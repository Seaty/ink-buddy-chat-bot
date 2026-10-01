"""Vision service: wires settings → AI layer; image upload, analysis, OCR, image-based product search, indexing.

The AI layer (ai/) knows nothing about settings, DB or HTTP; this is where
they meet. Retriever mode comes from ``IMAGE_RETRIEVER``: "mock" (no
embeddings needed) or "pgvector" (after the catalog is indexed).
"""
from __future__ import annotations

import logging
import time
from functools import lru_cache
from uuid import UUID

from PIL import Image
from sqlalchemy.orm import Session

from app.ai.embeddings.embedding_service import get_image_embedder
from app.ai.llm.ollama_client import OllamaClient, OllamaError
from app.ai.llm.qwen_vision import QwenVision, VisionModelError
from app.ai.prompts.vision_prompt import ImageAnalysis, MatchLevel
from app.ai.rag.chunker import CatalogChunk, build_catalog_chunks
from app.ai.rag.indexing_service import load_catalog
from app.ai.rag.retriever import ImageRetriever, MockCatalogRetriever, ProductRetriever
from app.ai.vision.image_analyzer import ImageAnalyzer
from app.ai.vision.ocr_service import OcrService
from app.ai.vision.vision_pipeline import InvalidImageError, PipelineSettings, VisionPipeline, load_upload
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.database import get_sessionmaker
from app.repositories.image_repository import ImageUpload, ImageUploadRepository
from app.repositories.product_repository import PgImageIndex, ProductRepository
from app.schemas.vision import (
    ImageAnalysisResponse,
    ImageAttributes,
    ImageOcrResponse,
    ImageUploadResponse,
    OcrSegmentOut,
    IndexCatalogResponse,
    ProductMatch,
    ProductSearchByImageResponse,
)
from app.services.image_storage import ImageStorage

logger = logging.getLogger(__name__)

# InvalidImageError.code → HTTP status (spec: 413 too large, 415 wrong type, 422 otherwise)
INVALID_IMAGE_STATUS = {"IMAGE_TOO_LARGE": 413, "UNSUPPORTED_MEDIA_TYPE": 415}


class VisionService:
    def __init__(
        self,
        settings: Settings,
        pipeline: VisionPipeline | None = None,
        storage: ImageStorage | None = None,
        ocr: OcrService | None = None,
    ):
        self.settings = settings
        self.pipeline = pipeline or self._build_pipeline()
        self.storage = storage or ImageStorage(settings.image_storage_dir)
        self._ocr = ocr

    # ------------------------------------------------------------------ wiring
    def _embedder(self):
        s = self.settings
        return get_image_embedder(s.image_embed_model, s.image_embed_device, s.image_embed_dim, s.image_embed_max_pixels)

    def _build_pipeline(self) -> VisionPipeline:
        s = self.settings
        vision = QwenVision(
            client=OllamaClient(s.ollama_base_url, s.ollama_timeout_s),
            model=s.vision_model,
            num_predict=s.vision_num_predict,
            num_ctx=s.vision_num_ctx,
        )
        retriever: ProductRetriever
        if s.image_retriever == "pgvector":
            retriever = ImageRetriever(
                self._embedder(), PgImageIndex(get_sessionmaker()), w_image=s.image_w_image, w_caption=s.image_w_caption
            )
        else:
            retriever = MockCatalogRetriever(s.catalog_dir)
        return VisionPipeline(
            ImageAnalyzer(vision),
            retriever,
            PipelineSettings(
                catalog_dir=s.catalog_dir,
                top_k=s.image_top_k,
                tau_similar=s.image_tau_similar,
                tau_suggest=s.image_tau_suggest,
                suggest_count=s.image_suggest_count,
                max_image_bytes=s.image_max_bytes,
                max_image_pixels=s.image_max_pixels,
                fast_path=s.image_fast_path,
                escalate_no_match=s.image_escalate_on_no_match,
            ),
        )

    # ------------------------------------------------------------------ upload
    def upload_image(self, db: Session, user_id: UUID, data: bytes) -> ImageUploadResponse:
        """Validate by content, store privately without metadata, record in image_uploads."""
        try:
            img = load_upload(data, self.settings.image_max_bytes, self.settings.image_max_pixels)
        except InvalidImageError as e:
            raise ApiError(INVALID_IMAGE_STATUS.get(e.code, 422), e.code, str(e)) from e

        stored = self.storage.save(img, img.format)
        try:
            row = ImageUploadRepository(db).create(user_id, stored.storage_key, stored.mime_type, stored.size_bytes)
            db.commit()
        except Exception:
            db.rollback()
            self.storage.delete(stored.storage_key)
            raise
        return ImageUploadResponse(id=row.id, status=row.status)

    # ------------------------------------------------------------------ search
    def search_by_image(self, db: Session, user_id: UUID, image_id: UUID, limit: int) -> ProductSearchByImageResponse:
        """Blocking (embedding, maybe VLM); call from a worker thread."""
        images = ImageUploadRepository(db)
        _, img = self._owned_image(images, user_id, image_id)
        with _vision_errors():
            result = self.pipeline.run(img, None, limit=limit, with_answer=False)

        catalog = ProductRepository(db).catalog_by_sku(p["sku"] for p in result.products + result.suggestions)
        matches = _to_matches(result.products[:limit], catalog,
                              lambda i: "exact" if i == 0 and result.match_level == MatchLevel.EXACT else "similar")
        suggestions = _to_matches(result.suggestions, catalog, lambda i: "suggestion")

        if result.analysis is not None:  # brand/model readings are not OCR: ocr_text is left alone
            images.save_analysis(image_id, result.analysis.model_dump(mode="json"))
            db.commit()

        return ProductSearchByImageResponse(
            image_id=image_id,
            description=result.analysis.description if result.analysis else None,
            match_level=result.match_level.value,
            matches=matches,
            path=result.path,
            timings_s=result.timings_s,
            suggestions=suggestions,
            message=result.answer if result.match_level == MatchLevel.NONE else None,
        )

    # ------------------------------------------------------------------ analysis / OCR
    def analyze_image(self, db: Session, user_id: UUID, image_id: UUID) -> ImageAnalysisResponse:
        """Vision-model reading of the photo; cached in image_uploads.analysis (also filled by a full-path search)."""
        images = ImageUploadRepository(db)
        upload = self._owned_upload(images, user_id, image_id)
        analysis = _cached_analysis(upload)
        cached = analysis is not None
        if analysis is None:
            _, img = self._owned_image(images, user_id, image_id)
            with _vision_errors():
                analysis = self.pipeline.analyzer.vision.analyze(img)
            images.save_analysis(image_id, analysis.model_dump(mode="json"))
            db.commit()
        return ImageAnalysisResponse(
            image_id=image_id,
            description=analysis.description,
            attributes=ImageAttributes(
                is_stationery=analysis.is_stationery, category=analysis.category_guess,
                brand_text=analysis.brand_text, model_text=analysis.model_text,
                colors=analysis.colors, features=analysis.attributes,
            ),
            cached=cached,
        )

    def ocr_image(self, db: Session, user_id: UUID, image_id: UUID) -> ImageOcrResponse:
        """Text printed on the item; cached in image_uploads.ocr_text."""
        images = ImageUploadRepository(db)
        upload = self._owned_upload(images, user_id, image_id)
        cached = upload.ocr_text is not None
        if cached:
            segments = [line for line in upload.ocr_text.split("\n") if line]
        else:
            _, img = self._owned_image(images, user_id, image_id)
            with _vision_errors():
                segments = self._ocr_service().read(img)
            images.save_ocr(image_id, "\n".join(segments))
            db.commit()
        return ImageOcrResponse(image_id=image_id, text="\n".join(segments),
                                segments=[OcrSegmentOut(text=t) for t in segments], cached=cached)

    def _ocr_service(self) -> OcrService:
        if self._ocr is None:
            self._ocr = OcrService(self.pipeline.analyzer.vision)
        return self._ocr

    # ------------------------------------------------------------------ shared
    def _owned_upload(self, images: ImageUploadRepository, user_id: UUID, image_id: UUID) -> ImageUpload:
        upload = images.get_owned(image_id, user_id)
        if upload is None:
            raise ApiError(404, "IMAGE_NOT_FOUND", "image not found")
        if upload.status != "ready":
            raise ApiError(422, "IMAGE_NOT_READY", f"image status is {upload.status}")
        return upload

    def _owned_image(self, images: ImageUploadRepository, user_id: UUID, image_id: UUID) -> tuple[ImageUpload, Image.Image]:
        upload = self._owned_upload(images, user_id, image_id)
        try:
            return upload, self.storage.open(upload.storage_key)
        except FileNotFoundError as e:
            raise ApiError(404, "IMAGE_NOT_FOUND", "image file is missing") from e

    # ------------------------------------------------------------------ indexing
    def index_catalog(self, session: Session) -> IndexCatalogResponse:
        """Embed new/changed chunks, refresh metadata of unchanged ones, drop removed ones.

        Raises CatalogError if metadata.csv has errors.
        """
        t0 = time.perf_counter()
        products, report = load_catalog(self.settings.catalog_dir, strict=True)
        chunks = build_catalog_chunks(products)
        embedder = self._embedder()
        repo = ProductRepository(session)

        existing = repo.existing_hashes(embedder.model_name)
        changed = [c for c in chunks if existing.get(_key(c)) != c.content_hash]
        unchanged = [c for c in chunks if existing.get(_key(c)) == c.content_hash]

        images = [c for c in changed if c.chunk_type == "image"]
        captions = [c for c in changed if c.chunk_type == "caption"]
        vectors = {}
        if images:
            embs = embedder.embed_images([Image.open(self.settings.catalog_dir / c.content) for c in images])
            vectors.update({_key(c): v for c, v in zip(images, embs)})
        if captions:
            embs = embedder.embed_texts([c.content for c in captions])
            vectors.update({_key(c): v for c, v in zip(captions, embs)})

        repo.upsert(
            {
                "sku": c.sku,
                "chunk_type": c.chunk_type,
                "variant": c.variant,
                "content": c.content,
                "content_hash": c.content_hash,
                "embedding": vectors[_key(c)],
                "embed_model": embedder.model_name,
                "meta": c.metadata,
            }
            for c in changed
        )
        repo.refresh_metadata({c.sku: c.metadata for c in unchanged})
        deleted = repo.delete_except({_key(c) for c in chunks})
        session.commit()

        return IndexCatalogResponse(
            products=len(products),
            chunks_embedded=len(changed),
            chunks_unchanged=len(unchanged),
            chunks_deleted=deleted,
            warnings=report.warnings,
            seconds=round(time.perf_counter() - t0, 2),
        )


def _to_matches(items: list[dict], catalog: dict[str, dict], match_type) -> list[ProductMatch]:
    """Retrieval hits → ProductMatch using products-table facts; ``match_type(i)`` labels position i."""
    out = []
    for p in items:
        row = catalog.get(p["sku"])
        if row is None:  # indexed but not seeded into products — never invent the product
            logger.warning("indexed sku %s missing from products table", p["sku"])
            continue
        out.append(ProductMatch(
            product_id=row["id"], sku=row["sku"], name=row["name"], category=row["category"],
            brand=row["brand"], price=float(row["price"]) if row["price"] is not None else None,
            currency=row["currency"], availability=row["availability"], source_ref=row["source_ref"],
            image_url=row["image_url"], match_type=match_type(len(out)), score=p["score"],
        ))
    return out


class _vision_errors:
    """Map model failures to 503 VISION_UNAVAILABLE."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None and issubclass(exc_type, (OllamaError, VisionModelError)):
            raise ApiError(503, "VISION_UNAVAILABLE", "vision model unavailable") from exc
        return False


def _cached_analysis(upload: ImageUpload) -> ImageAnalysis | None:
    if not upload.analysis:
        return None
    try:
        return ImageAnalysis.model_validate(upload.analysis)
    except ValueError:  # stored by an older schema → re-analyse
        return None


def _key(c: CatalogChunk) -> tuple[str, str, int]:
    return (c.sku, c.chunk_type, c.variant)


@lru_cache(maxsize=1)
def get_vision_service() -> VisionService:
    """FastAPI dependency; one pipeline (and one loaded model) per process."""
    return VisionService(get_settings())
