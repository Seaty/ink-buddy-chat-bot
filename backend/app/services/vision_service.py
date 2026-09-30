"""Vision service: wires settings → AI layer; image upload, image-based product search, catalog indexing.

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
from app.ai.prompts.vision_prompt import MatchLevel
from app.ai.rag.chunker import CatalogChunk, build_catalog_chunks
from app.ai.rag.indexing_service import load_catalog
from app.ai.rag.retriever import ImageRetriever, MockCatalogRetriever, ProductRetriever
from app.ai.vision.image_analyzer import ImageAnalyzer
from app.ai.vision.vision_pipeline import InvalidImageError, PipelineSettings, VisionPipeline, load_upload
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.database import get_sessionmaker
from app.repositories.image_repository import ImageUploadRepository
from app.repositories.product_repository import PgImageIndex, ProductRepository
from app.schemas.vision import (
    ImageUploadResponse,
    IndexCatalogResponse,
    ProductMatch,
    ProductSearchByImageResponse,
)
from app.services.image_storage import ImageStorage

logger = logging.getLogger(__name__)

# InvalidImageError.code → HTTP status (spec: 413 too large, 415 wrong type, 422 otherwise)
INVALID_IMAGE_STATUS = {"IMAGE_TOO_LARGE": 413, "UNSUPPORTED_MEDIA_TYPE": 415}


class VisionService:
    def __init__(self, settings: Settings, pipeline: VisionPipeline | None = None, storage: ImageStorage | None = None):
        self.settings = settings
        self.pipeline = pipeline or self._build_pipeline()
        self.storage = storage or ImageStorage(settings.image_storage_dir)

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
                tau_exact=s.image_tau_exact,
                tau_similar=s.image_tau_similar,
                max_image_bytes=s.image_max_bytes,
                max_image_pixels=s.image_max_pixels,
                fast_path=s.image_fast_path,
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
        upload = images.get_owned(image_id, user_id)
        if upload is None:
            raise ApiError(404, "IMAGE_NOT_FOUND", "image not found")
        if upload.status != "ready":
            raise ApiError(422, "IMAGE_NOT_READY", f"image status is {upload.status}")
        try:
            img = self.storage.open(upload.storage_key)
        except FileNotFoundError as e:
            raise ApiError(404, "IMAGE_NOT_FOUND", "image file is missing") from e

        try:
            result = self.pipeline.run(img, None, limit=limit, with_answer=False)
        except (OllamaError, VisionModelError) as e:
            raise ApiError(503, "VISION_UNAVAILABLE", "vision model unavailable") from e

        catalog = ProductRepository(db).catalog_by_sku(p["sku"] for p in result.products)
        matches = []
        for p in result.products[:limit]:
            row = catalog.get(p["sku"])
            if row is None:  # indexed but not seeded into products — never invent the product
                logger.warning("indexed sku %s missing from products table", p["sku"])
                continue
            exact = result.match_level == MatchLevel.EXACT and not matches
            matches.append(ProductMatch(
                product_id=row["id"], sku=row["sku"], name=row["name"], category=row["category"],
                brand=row["brand"], price=float(row["price"]) if row["price"] is not None else None,
                currency=row["currency"], availability=row["availability"], source_ref=row["source_ref"],
                image_url=row["image_url"], match_type="exact" if exact else "similar", score=p["score"],
            ))

        if result.analysis is not None:
            a = result.analysis
            images.save_analysis(image_id, a.model_dump(mode="json"), " ".join(filter(None, [a.brand_text, a.model_text])))
            db.commit()

        return ProductSearchByImageResponse(
            image_id=image_id,
            description=result.analysis.description if result.analysis else None,
            match_level=result.match_level.value,
            matches=matches,
            path=result.path,
            timings_s=result.timings_s,
        )

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


def _key(c: CatalogChunk) -> tuple[str, str, int]:
    return (c.sku, c.chunk_type, c.variant)


@lru_cache(maxsize=1)
def get_vision_service() -> VisionService:
    """FastAPI dependency; one pipeline (and one loaded model) per process."""
    return VisionService(get_settings())
