"""Vision service: wires settings → AI layer, and runs search / catalog indexing.

The AI layer (ai/) knows nothing about settings, DB or HTTP; this is where
they meet. Retriever mode comes from ``IMAGE_RETRIEVER``: "mock" (default,
no embeddings needed) or "pgvector" (after POST /api/vision/index).
"""
from __future__ import annotations

import time
from functools import lru_cache

from PIL import Image
from sqlalchemy.orm import Session

from ai.embeddings.embedding_service import get_image_embedder
from ai.llm.ollama_client import OllamaClient
from ai.llm.qwen_vision import QwenVision
from ai.rag.chunker import CatalogChunk, build_catalog_chunks
from ai.rag.indexing_service import load_catalog
from ai.rag.retriever import ImageRetriever, MockCatalogRetriever, ProductRetriever
from ai.vision.image_analyzer import ImageAnalyzer
from ai.vision.vision_pipeline import PipelineSettings, VisionPipeline
from core.config import Settings, get_settings
from core.database import get_sessionmaker
from repositories.product_repository import PgImageIndex, ProductRepository
from schemas.vision import IndexCatalogResponse, VisionSearchResponse


class VisionService:
    def __init__(self, settings: Settings, pipeline: VisionPipeline | None = None):
        self.settings = settings
        self.pipeline = pipeline or self._build_pipeline()

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
            ),
        )

    # ------------------------------------------------------------------ search
    def search(self, image: bytes, message: str | None) -> VisionSearchResponse:
        """Blocking (VLM + embedding); call from a worker thread."""
        result = self.pipeline.run(image, message)
        return VisionSearchResponse.model_validate(result.to_dict())

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
