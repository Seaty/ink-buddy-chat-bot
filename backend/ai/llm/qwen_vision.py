"""Qwen3-VL wrapper (via Ollama): image analysis, catalog captions, answers.

Note: ``qwen3-vl:latest`` is a thinking model and ignores ``think=false`` — it
writes a long reasoning trace (``thinking``) before the answer. ``num_predict``
must leave room for that, or the JSON gets cut off. An instruct tag avoids
both the trace and the latency; set VISION_MODEL to switch.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
from typing import Sequence

from PIL import Image, ImageOps
from pydantic import ValidationError

from ai.llm.ollama_client import OllamaClient
from ai.prompts.vision_prompt import (
    CAPTION_PROMPT,
    IMAGE_ANALYSIS_PROMPT,
    IMAGE_ANALYSIS_SCHEMA,
    ImageAnalysis,
    sanitize_user_text,
)

DEFAULT_MODEL = "qwen3-vl:latest"
VLM_MAX_SIDE = 1024
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class VisionModelError(RuntimeError):
    pass


def encode_image(img: Image.Image, max_side: int = VLM_MAX_SIDE) -> str:
    """JPEG base64 for Ollama. Keeps aspect ratio (no padding) so the model's
    0-1000 bbox maps straight back onto the original image."""
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        rgba = img.convert("RGBA")
        img = Image.new("RGB", rgba.size, "white")
        img.paste(rgba, mask=rgba.getchannel("A"))
    if max(img.size) > max_side:
        img = img.copy()
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _clean(content: str) -> str:
    return _THINK_BLOCK.sub("", content or "").strip()


def _extract_json(text: str) -> str:
    """Tolerate ```json fences or prose around the object."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    return text[start : end + 1]


class QwenVision:
    def __init__(
        self,
        client: OllamaClient | None = None,
        model: str | None = None,
        num_predict: int = 6144,
        keep_alive: str = "30m",
    ):
        self.client = client or OllamaClient()
        self.model = model or os.getenv("VISION_MODEL", DEFAULT_MODEL)
        self.num_predict = num_predict
        self.keep_alive = keep_alive

    def _chat(self, messages: list[dict], *, format=None, temperature: float = 0.0) -> str:
        resp = self.client.chat(
            self.model,
            messages,
            format=format,
            think=False,
            keep_alive=self.keep_alive,
            options={"temperature": temperature, "num_predict": self.num_predict},
        )
        content = _clean(resp.get("message", {}).get("content", ""))
        if not content:
            reason = resp.get("done_reason")
            raise VisionModelError(
                f"empty answer from {self.model} (done_reason={reason}); "
                "if 'length', the thinking trace used up num_predict"
            )
        return content

    def analyze(self, image: Image.Image, message: str | None = None, retries: int = 1) -> ImageAnalysis:
        """Call #1: structured understanding of the customer photo."""
        messages = [{
            "role": "user",
            "content": IMAGE_ANALYSIS_PROMPT.format(message=sanitize_user_text(message)),
            "images": [encode_image(image)],
        }]
        last_error: Exception | None = None
        for _ in range(retries + 1):
            content = self._chat(messages, format=IMAGE_ANALYSIS_SCHEMA)
            try:
                return ImageAnalysis.model_validate(json.loads(_extract_json(content)))
            except (ValueError, ValidationError) as e:
                last_error = e
        raise VisionModelError(f"invalid analysis JSON: {last_error}")

    def caption(self, image: Image.Image, name: str) -> str:
        """Indexing: short Thai visual description of a catalog photo."""
        return self._chat([{
            "role": "user",
            "content": CAPTION_PROMPT.format(name=name),
            "images": [encode_image(image)],
        }])

    def answer(
        self,
        system_prompt: str,
        user_prompt: str,
        images: Sequence[Image.Image] = (),
        temperature: float = 0.3,
    ) -> str:
        """Call #2: grounded answer. ``images`` are attached in order (e.g. for compare)."""
        user: dict = {"role": "user", "content": user_prompt}
        if images:
            user["images"] = [encode_image(img) for img in images]
        return self._chat([{"role": "system", "content": system_prompt}, user], temperature=temperature)
