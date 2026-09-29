"""Image RAG query pipeline (IMAGE_RAG_DESIGN.md §1.3).

image + message
  → validate → ImageAnalyzer (qwen3-vl call #1 + crop)
  → intent → retrieve + filter → match level
  → answer (price/stock in Python; otherwise qwen3-vl call #2)

Retrieval sits behind ``ProductRetriever`` (ai/rag/retriever.py):
``ImageRetriever`` over pgvector, or ``MockCatalogRetriever`` before the
catalog is embedded.
"""
from __future__ import annotations

import io
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence

from PIL import Image

from ai.prompts.vision_prompt import (
    OUT_OF_SCOPE_ANSWER,
    VISION_SYSTEM_PROMPT,
    Constraints,
    ImageAnalysis,
    Intent,
    MatchLevel,
    build_answer_prompt,
    price_stock_answer,
    resolve_intent,
)
from ai.rag.retriever import MockCatalogRetriever, ProductRetriever, RetrievalQuery, normalize_key
from ai.vision.image_analyzer import AnalyzedImage, ImageAnalyzer

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MIN_IMAGE_SIDE = 32
CHEAPER_WORDS = ("ถูกกว่า", "ประหยัดกว่า", "cheaper")


@dataclass(frozen=True)
class PipelineSettings:
    """Built from core/config.py by services/vision_service.py."""

    catalog_dir: Path = BACKEND_DIR / "datasets" / "catalog"
    top_k: int = 5
    tau_exact: float = 0.80
    tau_similar: float = 0.55
    max_image_bytes: int = 5 * 1024 * 1024
    compare_items: int = 2


class InvalidImageError(ValueError):
    """Upload is not an acceptable image (maps to HTTP 400/413)."""


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------
@dataclass
class VisionResult:
    answer: str
    intent: Intent
    match_level: MatchLevel
    products: list[dict] = field(default_factory=list)
    needs_confirmation: bool = False
    analysis: ImageAnalysis | None = None
    timings_s: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["intent"] = self.intent.value
        d["match_level"] = self.match_level.value
        d["analysis"] = self.analysis.model_dump(mode="json") if self.analysis else None
        return d


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def load_upload(data: bytes, max_bytes: int) -> Image.Image:
    """Validate and decode an uploaded image. TODO: move to ai/guards once it exists."""
    if not data:
        raise InvalidImageError("empty upload")
    if len(data) > max_bytes:
        raise InvalidImageError(f"image larger than {max_bytes // (1024 * 1024)} MB")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            probe.verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except Image.DecompressionBombError as e:
        raise InvalidImageError("image dimensions too large") from e
    except Exception as e:  # noqa: BLE001 — any decode failure is a bad upload
        raise InvalidImageError("file is not a readable image") from e
    if fmt not in ALLOWED_FORMATS:
        raise InvalidImageError(f"unsupported format {fmt}; use JPEG, PNG or WEBP")
    if min(img.size) < MIN_IMAGE_SIDE:
        raise InvalidImageError("image too small")
    return img


def match_level_for(score: float | None, settings: PipelineSettings) -> MatchLevel:
    if score is None or score < settings.tau_similar:
        return MatchLevel.NONE
    return MatchLevel.EXACT if score >= settings.tau_exact else MatchLevel.SIMILAR


def _piece_price(p: dict) -> float:
    return p["unit_price"] if p.get("unit_price") is not None else p["price_thb"]


def apply_constraints(products: Sequence[dict], c: Constraints) -> list[dict]:
    out = []
    for p in products:
        if c.max_price is not None and p["price_thb"] > c.max_price:
            continue
        if c.in_stock_only and p.get("stock_qty") == 0:
            continue
        if c.brand and normalize_key(c.brand) not in normalize_key(p["brand"]):
            continue
        if c.color and normalize_key(c.color) not in normalize_key(p["name"]) and normalize_key(c.color) not in normalize_key(p.get("color", "")):
            continue
        out.append(p)
    return out


class VisionPipeline:
    def __init__(
        self,
        analyzer: ImageAnalyzer | None = None,
        retriever: ProductRetriever | None = None,
        settings: PipelineSettings | None = None,
    ):
        self.settings = settings or PipelineSettings()
        self.analyzer = analyzer or ImageAnalyzer()
        self.retriever = retriever or MockCatalogRetriever(self.settings.catalog_dir)

    def run(self, image: bytes | Image.Image, message: str | None = None) -> VisionResult:
        timings: dict[str, float] = {}
        t0 = time.perf_counter()

        img = image if isinstance(image, Image.Image) else load_upload(image, self.settings.max_image_bytes)

        t = time.perf_counter()
        analyzed = self.analyzer.analyze(img, message)
        timings["analyze"] = time.perf_counter() - t
        analysis = analyzed.analysis
        intent = resolve_intent(message, analysis)

        if intent == Intent.OUT_OF_SCOPE:
            timings["total"] = time.perf_counter() - t0
            return VisionResult(OUT_OF_SCOPE_ANSWER, intent, MatchLevel.NONE, analysis=analysis, timings_s=timings)

        t = time.perf_counter()
        candidates = self.retriever.search(self._query(analyzed), top_k=self.settings.top_k * 2)
        timings["retrieve"] = time.perf_counter() - t
        # Match level says whether *this* item is in the store, so it uses the
        # unfiltered best hit; customer constraints only narrow what we show.
        match_level = match_level_for(candidates[0]["score"] if candidates else None, self.settings)

        if intent == Intent.PRICE_STOCK:
            products = candidates[: self.settings.top_k]
            answer, confirm = price_stock_answer(products, match_level)
            timings["total"] = time.perf_counter() - t0
            return VisionResult(answer, intent, match_level, products, confirm, analysis, timings)

        products = self._select(intent, message, analysis, candidates, match_level)
        images = self._images_for(intent, analyzed, products)

        t = time.perf_counter()
        prompt = build_answer_prompt(intent, message, analysis, products, match_level)
        answer = self.analyzer.vision.answer(VISION_SYSTEM_PROMPT, prompt, images)
        timings["answer"] = time.perf_counter() - t
        timings["total"] = time.perf_counter() - t0
        return VisionResult(answer, intent, match_level, products, False, analysis, timings)

    @staticmethod
    def _query(analyzed: AnalyzedImage) -> RetrievalQuery:
        a = analyzed.analysis
        text = " ".join(filter(None, [a.description, a.brand_text, a.model_text, *a.attributes]))
        return RetrievalQuery(image=analyzed.cropped, text=text, analysis=a)

    def _select(
        self,
        intent: Intent,
        message: str | None,
        analysis: ImageAnalysis,
        candidates: list[dict],
        match_level: MatchLevel,
    ) -> list[dict]:
        k = self.settings.top_k
        if match_level == MatchLevel.NONE:
            # nothing close: offer same-category items only
            candidates = [p for p in candidates if p["category"] == analysis.category_guess]
        else:
            # never pad the list with unrelated items below the similarity bar
            candidates = [p for p in candidates if p["score"] >= self.settings.tau_similar]
        if intent == Intent.RECOMMEND:
            products = apply_constraints(candidates, analysis.constraints)
            if candidates and any(w in (message or "").lower() for w in CHEAPER_WORDS):
                ref = candidates[0]
                products = [p for p in products if p["sku"] != ref["sku"] and _piece_price(p) < _piece_price(ref)]
            return products[:k]
        if intent == Intent.COMPARE:
            return candidates[: self.settings.compare_items]
        if intent == Intent.GENERAL:
            return candidates[:1]
        return candidates[:3]  # FIND_SIMILAR

    def _images_for(self, intent: Intent, analyzed: AnalyzedImage, products: list[dict]) -> list[Image.Image]:
        """Only COMPARE needs pixels in call #2: customer item first, then catalog items."""
        if intent != Intent.COMPARE:
            return []
        return [analyzed.cropped] + [Image.open(self.settings.catalog_dir / p["image_path"]) for p in products]


if __name__ == "__main__":
    import json
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        sys.exit("usage: python -m ai.vision.vision_pipeline <image> [message]")
    # same wiring as the API, so backend/.env applies here too
    from core.config import get_settings
    from services.vision_service import VisionService

    pipeline = VisionService(get_settings()).pipeline
    result = pipeline.run(Path(sys.argv[1]).read_bytes(), sys.argv[2] if len(sys.argv) > 2 else None)
    out = result.to_dict()
    out["products"] = [{k: p[k] for k in ("sku", "name", "price_thb", "score")} for p in out["products"]]
    print(json.dumps(out, ensure_ascii=False, indent=1))
