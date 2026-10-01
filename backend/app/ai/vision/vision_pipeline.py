"""Image RAG query pipeline (IMAGE_RAG_DESIGN.md §1.3).

image + message
  → validate
  → FAST PATH (find_similar / price_stock by keyword rules, or image only):
      embed full image → retrieve → match level → template answer (no LLM).
      No confident match → fall through to the full path.
  → FULL PATH: ImageAnalyzer (qwen3-vl call #1 + crop)
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

from app.ai.prompts.vision_prompt import (
    OUT_OF_SCOPE_ANSWER,
    VISION_SYSTEM_PROMPT,
    Constraints,
    ImageAnalysis,
    Intent,
    MatchLevel,
    build_answer_prompt,
    detect_intent_by_rules,
    find_similar_answer,
    price_stock_answer,
    resolve_intent,
)
from app.ai.rag.retriever import MockCatalogRetriever, ProductRetriever, RetrievalQuery, normalize_key
from app.ai.vision.image_analyzer import AnalyzedImage, ImageAnalyzer

BACKEND_DIR = Path(__file__).resolve().parents[3]
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MIN_IMAGE_SIDE = 32
CHEAPER_WORDS = ("ถูกกว่า", "ประหยัดกว่า", "cheaper")
# Intents the fast path can answer from retrieval alone (no VLM).
FAST_INTENTS = (Intent.FIND_SIMILAR, Intent.PRICE_STOCK)
SIMILAR_SHOWN = 3


@dataclass(frozen=True)
class PipelineSettings:
    """Built from core/config.py by services/vision_service.py."""

    catalog_dir: Path = BACKEND_DIR / "datasets" / "catalog"
    top_k: int = 5
    tau_exact: float = 0.80
    tau_similar: float = 0.55
    max_image_bytes: int = 5 * 1024 * 1024
    max_image_pixels: int = 40_000_000
    compare_items: int = 2
    fast_path: bool = True


class InvalidImageError(ValueError):
    """Upload is not an acceptable image. ``code`` is mapped to an HTTP status by the API layer:
    EMPTY_FILE / IMAGE_TOO_SMALL → 422, IMAGE_TOO_LARGE → 413, UNSUPPORTED_MEDIA_TYPE → 415."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


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
    path: str = "full"  # "fast" = answered without the VLM

    def to_dict(self) -> dict:
        d = asdict(self)
        d["intent"] = self.intent.value
        d["match_level"] = self.match_level.value
        d["analysis"] = self.analysis.model_dump(mode="json") if self.analysis else None
        return d


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def load_upload(data: bytes, max_bytes: int, max_pixels: int = 40_000_000) -> Image.Image:
    """Validate and decode an uploaded image by its content (not its filename or header).

    TODO: move to ai/guards once it exists.
    """
    if not data:
        raise InvalidImageError("empty upload", "EMPTY_FILE")
    if len(data) > max_bytes:
        raise InvalidImageError(f"image larger than {max_bytes // (1024 * 1024)} MB", "IMAGE_TOO_LARGE")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt, (w, h) = probe.format, probe.size
            probe.verify()
    except Image.DecompressionBombError as e:
        raise InvalidImageError("image dimensions too large", "IMAGE_TOO_LARGE") from e
    except Exception as e:  # noqa: BLE001 — any decode failure is a bad upload
        raise InvalidImageError("file is not a readable image", "UNSUPPORTED_MEDIA_TYPE") from e
    if fmt not in ALLOWED_FORMATS:
        raise InvalidImageError(f"unsupported format {fmt}; use JPEG, PNG or WEBP", "UNSUPPORTED_MEDIA_TYPE")
    if w * h > max_pixels:
        raise InvalidImageError(f"image has more than {max_pixels:,} pixels", "IMAGE_TOO_LARGE")
    if min(w, h) < MIN_IMAGE_SIDE:
        raise InvalidImageError("image too small", "IMAGE_TOO_SMALL")
    img = Image.open(io.BytesIO(data))
    img.load()
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

    def run(
        self,
        image: bytes | Image.Image,
        message: str | None = None,
        limit: int | None = None,
        with_answer: bool = True,
    ) -> VisionResult:
        """``limit`` caps the products shown for find-similar (default 3).
        ``with_answer=False`` skips the second VLM call (search-only callers)."""
        timings: dict[str, float] = {}
        t0 = time.perf_counter()

        img = image if isinstance(image, Image.Image) else load_upload(
            image, self.settings.max_image_bytes, self.settings.max_image_pixels
        )
        shown = limit or SIMILAR_SHOWN

        rule_intent = detect_intent_by_rules(message)
        if self.settings.fast_path and rule_intent in FAST_INTENTS:
            fast = self._run_fast(img, rule_intent, timings, t0, shown)
            if fast is not None:
                return fast

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

        products = self._select(intent, message, analysis, candidates, match_level, shown)
        if not with_answer:
            timings["total"] = time.perf_counter() - t0
            return VisionResult("", intent, match_level, products, False, analysis, timings)
        images = self._images_for(intent, analyzed, products)

        t = time.perf_counter()
        prompt = build_answer_prompt(intent, message, analysis, products, match_level)
        answer = self.analyzer.vision.answer(VISION_SYSTEM_PROMPT, prompt, images)
        timings["answer"] = time.perf_counter() - t
        timings["total"] = time.perf_counter() - t0
        return VisionResult(answer, intent, match_level, products, False, analysis, timings)

    def _run_fast(self, img: Image.Image, intent: Intent, timings: dict, t0: float, shown: int) -> VisionResult | None:
        """Retrieval-only answer. Returns None (→ full path) when nothing matches confidently.

        Without the VLM there is no crop, category, brand or is-stationery check,
        so a NONE match is escalated: the VLM can crop a cluttered photo or
        recognise that the item is not stationery at all.
        """
        placeholder = ImageAnalysis(is_stationery=True, intent=intent, category_guess="other", description="")
        t = time.perf_counter()
        candidates = self.retriever.search(RetrievalQuery(img, "", placeholder), top_k=self.settings.top_k * 2)
        timings["retrieve_fast"] = time.perf_counter() - t
        match_level = match_level_for(candidates[0]["score"] if candidates else None, self.settings)
        if match_level == MatchLevel.NONE:
            return None

        if intent == Intent.PRICE_STOCK:
            products = candidates[: self.settings.top_k]
            answer, confirm = price_stock_answer(products, match_level)
        else:
            products = [p for p in candidates if p["score"] >= self.settings.tau_similar][:shown]
            answer, confirm = find_similar_answer(products, match_level), False
        timings["total"] = time.perf_counter() - t0
        return VisionResult(answer, intent, match_level, products, confirm, None, timings, path="fast")

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
        shown: int = SIMILAR_SHOWN,
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
        return candidates[:shown]  # FIND_SIMILAR

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
        sys.exit("usage: python -m app.ai.vision.vision_pipeline <image> [message]")
    # same wiring as the API, so backend/.env applies here too
    from app.core.config import get_settings
    from app.services.vision_service import VisionService

    pipeline = VisionService(get_settings()).pipeline
    result = pipeline.run(Path(sys.argv[1]).read_bytes(), sys.argv[2] if len(sys.argv) > 2 else None)
    out = result.to_dict()
    out["products"] = [{k: p[k] for k in ("sku", "name", "price_thb", "score")} for p in out["products"]]
    print(json.dumps(out, ensure_ascii=False, indent=1))
