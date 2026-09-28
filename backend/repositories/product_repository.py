"""Data access for product_image_embeddings (Image RAG)."""
from __future__ import annotations

from collections.abc import Callable, Iterable

import numpy as np
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from models.product import ProductImageEmbedding as Row

ChunkKey = tuple[str, str, int]  # (sku, chunk_type, variant)


class ProductRepository:
    def __init__(self, session: Session):
        self.session = session

    def existing_hashes(self, embed_model: str) -> dict[ChunkKey, str]:
        """content_hash of chunks already embedded with ``embed_model``."""
        rows = self.session.execute(
            select(Row.sku, Row.chunk_type, Row.variant, Row.content_hash).where(Row.embed_model == embed_model)
        )
        return {(r.sku, r.chunk_type, r.variant): r.content_hash for r in rows}

    def upsert(self, rows: Iterable[dict]) -> int:
        """Insert or replace chunks.

        Each dict: sku, chunk_type, variant, content, content_hash, embedding, embed_model, meta.
        """
        rows = [{("metadata" if k == "meta" else k): v for k, v in r.items()} for r in rows]
        if not rows:
            return 0
        table = Row.__table__  # Core insert: keys are column names ("metadata", not "meta")
        stmt = insert(table).values(rows)
        replace = ("content", "content_hash", "embedding", "embed_model", "metadata")
        stmt = stmt.on_conflict_do_update(
            constraint="uq_product_chunk",
            set_={**{name: stmt.excluded[name] for name in replace}, "updated_at": func.now()},
        )
        self.session.execute(stmt)
        return len(rows)

    def refresh_metadata(self, metadata_by_sku: dict[str, dict]) -> None:
        """Price/stock changes: update JSONB without re-embedding."""
        for sku, meta in metadata_by_sku.items():
            self.session.execute(update(Row).where(Row.sku == sku).values(meta=meta))

    def delete_except(self, keep: set[ChunkKey]) -> int:
        """Remove chunks whose (sku, chunk_type, variant) is not in ``keep``."""
        existing = self.session.execute(select(Row.id, Row.sku, Row.chunk_type, Row.variant)).all()
        stale = [r.id for r in existing if (r.sku, r.chunk_type, r.variant) not in keep]
        if stale:
            self.session.execute(delete(Row).where(Row.id.in_(stale)))
        return len(stale)

    def best_by_sku(self, vector: np.ndarray, chunk_type: str, limit: int) -> dict[str, tuple[float, dict]]:
        """Cosine similarity, best chunk per SKU, active products only."""
        distance = Row.embedding.cosine_distance(np.asarray(vector, dtype=np.float32))
        rows = self.session.execute(
            select(Row.sku, Row.meta, (1 - distance).label("similarity"))
            .where(Row.chunk_type.in_(_types_for(chunk_type)))
            .where(Row.meta["is_active"].as_boolean().is_not(False))
            .order_by(distance)
            .limit(limit * 3)  # several chunks can belong to one SKU (image + image_aug)
        )
        best: dict[str, tuple[float, dict]] = {}
        for r in rows:
            if r.sku not in best:  # rows are ordered best-first
                best[r.sku] = (float(r.similarity), r.meta)
            if len(best) == limit:
                break
        return best

    def count(self) -> int:
        return len(self.session.execute(select(Row.id)).all())


def _types_for(chunk_type: str) -> tuple[str, ...]:
    # augmented views count as image evidence for the same SKU
    return ("image", "image_aug") if chunk_type == "image" else (chunk_type,)


class PgImageIndex:
    """ImageVectorIndex (ai/rag/retriever.py) backed by pgvector; one session per search."""

    def __init__(self, session_factory: Callable[[], Session]):
        self.session_factory = session_factory

    def best_by_sku(self, vector: np.ndarray, chunk_type: str, limit: int) -> dict[str, tuple[float, dict]]:
        with self.session_factory() as session:
            return ProductRepository(session).best_by_sku(vector, chunk_type, limit)
