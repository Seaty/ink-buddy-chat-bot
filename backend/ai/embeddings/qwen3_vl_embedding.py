"""Qwen3-VL-Embedding-2B — multimodal (image + text) embeddings for Image RAG.

Runs through Hugging Face transformers, not Ollama: the Ollama build
(MedAIBase/Qwen3-VL-Embedding:2b) exposes neither the embedding nor the vision
capability.

Adapted from the model's reference script
(https://huggingface.co/Qwen/Qwen3-VL-Embedding-2B/blob/main/scripts/qwen3_vl_embedding.py),
reduced to image + text input. Unlike the reference script, a vision
preprocessing error raises instead of silently embedding the text "NULL".
"""
from __future__ import annotations

import io
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, Union

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps
from qwen_vl_utils import process_vision_info
from transformers.modeling_outputs import ModelOutput
from transformers.models.qwen3_vl.modeling_qwen3_vl import (
    Qwen3VLConfig,
    Qwen3VLModel,
    Qwen3VLPreTrainedModel,
)
from transformers.models.qwen3_vl.processing_qwen3_vl import Qwen3VLProcessor

ImageInput = Union[str, Path, bytes, Image.Image]

DEFAULT_MODEL = "Qwen/Qwen3-VL-Embedding-2B"
DEFAULT_INSTRUCTION = "Represent the user's input."
FULL_DIM = 2048
MAX_LENGTH = 8192
IMAGE_PATCH_SIZE = 16
IMAGE_FACTOR = IMAGE_PATCH_SIZE * 2
MIN_PIXELS = 4 * IMAGE_FACTOR * IMAGE_FACTOR
DEFAULT_MAX_PIXELS = 800 * 800
IMAGE_MAX_SIDE = 1024


@dataclass
class _EmbeddingOutput(ModelOutput):
    last_hidden_state: torch.FloatTensor | None = None


class _Qwen3VLForEmbedding(Qwen3VLPreTrainedModel):
    """Wraps Qwen3VLModel so checkpoint keys (``model.*``) load unchanged."""

    config: Qwen3VLConfig

    def __init__(self, config):
        super().__init__(config)
        self.model = Qwen3VLModel(config)
        self.post_init()

    def forward(self, **inputs) -> _EmbeddingOutput:
        return _EmbeddingOutput(last_hidden_state=self.model(**inputs).last_hidden_state)


def prepare_image(src: ImageInput, max_side: int = IMAGE_MAX_SIDE) -> Image.Image:
    """Normalize an image the same way for catalog indexing and customer queries.

    EXIF orientation → RGB on white (for transparent PNGs) → pad to a white
    square (catalog photos are square, white background) → cap the long side.
    """
    if isinstance(src, Image.Image):
        img = src
    elif isinstance(src, bytes):
        img = Image.open(io.BytesIO(src))
    else:
        img = Image.open(src)
    img = ImageOps.exif_transpose(img)

    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img, mask=img.getchannel("A"))
        img = bg
    else:
        img = img.convert("RGB")

    side = max(img.size)
    if img.width != img.height:
        square = Image.new("RGB", (side, side), "white")
        square.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
        img = square
    if side > max_side:
        img = img.resize((max_side, max_side), Image.Resampling.LANCZOS)
    return img


def _with_period(instruction: str) -> str:
    instruction = instruction.strip()
    if instruction and not unicodedata.category(instruction[-1]).startswith("P"):
        instruction += "."
    return instruction


class Qwen3VLEmbedding:
    """Image/text embedder sharing one vector space (cosine on L2-normalized vectors).

    Use ``instruction`` for queries only; catalog items use the default
    instruction, following the Qwen embedding convention.
    """

    def __init__(
        self,
        model_name_or_path: str = DEFAULT_MODEL,
        device: str | None = None,
        dim: int = FULL_DIM,
        max_pixels: int = DEFAULT_MAX_PIXELS,
        batch_size: int = 4,
    ):
        if not 64 <= dim <= FULL_DIM:
            raise ValueError(f"dim must be in [64, {FULL_DIM}] (MRL), got {dim}")
        self.model_name = model_name_or_path
        self.dim = dim
        self.max_pixels = max_pixels
        self.batch_size = batch_size
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        dtype = torch.float16 if self.device.type == "cuda" else torch.float32

        self.model = _Qwen3VLForEmbedding.from_pretrained(model_name_or_path, dtype=dtype).to(self.device)
        self.model.eval()
        self.processor = Qwen3VLProcessor.from_pretrained(model_name_or_path, padding_side="right")
        self._lock = threading.Lock()

    def embed_images(self, images: Sequence[ImageInput], instruction: str | None = None) -> np.ndarray:
        return self._embed([{"image": img, "instruction": instruction} for img in images])

    def embed_texts(self, texts: Sequence[str], instruction: str | None = None) -> np.ndarray:
        return self._embed([{"text": t, "instruction": instruction} for t in texts])

    def embed_image_text(self, image: ImageInput, text: str, instruction: str | None = None) -> np.ndarray:
        """One fused vector for an image plus its text (e.g. a customer photo + message)."""
        return self._embed([{"image": image, "text": text, "instruction": instruction}])[0]

    def _embed(self, items: list[dict]) -> np.ndarray:
        if not items:
            return np.zeros((0, self.dim), dtype=np.float32)
        chunks = [
            self._embed_batch(items[i : i + self.batch_size])
            for i in range(0, len(items), self.batch_size)
        ]
        return np.concatenate(chunks)

    def _conversation(self, item: dict) -> list[dict]:
        content = []
        if item.get("image") is not None:
            content.append({
                "type": "image",
                "image": prepare_image(item["image"]),
                "min_pixels": MIN_PIXELS,
                "max_pixels": self.max_pixels,
            })
        if item.get("text"):
            content.append({"type": "text", "text": item["text"]})
        if not content:
            raise ValueError("embedding input needs an image or non-empty text")
        instruction = _with_period(item.get("instruction") or DEFAULT_INSTRUCTION)
        return [
            {"role": "system", "content": [{"type": "text", "text": instruction}]},
            {"role": "user", "content": content},
        ]

    @torch.inference_mode()
    def _embed_batch(self, items: list[dict]) -> np.ndarray:
        conversations = [self._conversation(item) for item in items]
        text = self.processor.apply_chat_template(conversations, add_generation_prompt=True, tokenize=False)
        images, _ = process_vision_info(conversations, image_patch_size=IMAGE_PATCH_SIZE)
        inputs = self.processor(
            text=text,
            images=images,
            truncation=True,
            max_length=MAX_LENGTH,
            padding=True,
            do_resize=False,
            return_tensors="pt",
        ).to(self.device)

        with self._lock:
            hidden = self.model(**inputs).last_hidden_state

        # last-token pooling (padding is on the right)
        mask = inputs["attention_mask"]
        last = mask.shape[1] - mask.flip(dims=[1]).argmax(dim=1) - 1
        emb = hidden[torch.arange(hidden.shape[0], device=hidden.device), last]
        emb = F.normalize(emb.float()[:, : self.dim], p=2, dim=-1)
        return emb.cpu().numpy()
