"""Catalog embeddings for Image RAG (docs/architecture/IMAGE_RAG_DESIGN.md §2.5).

One row per chunk (image / caption / image_aug) per SKU. Product data lives in
``metadata`` JSONB, synced from datasets/catalog/metadata.csv (source of truth).
Separate from the text-RAG table: different model, different vector space.
"""
from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, Index, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

IMAGE_EMBED_DIM = 2048
CHUNK_TYPES = ("image", "image_aug", "caption")


class ProductImageEmbedding(Base):
    __tablename__ = "product_image_embeddings"
    __table_args__ = (
        UniqueConstraint("sku", "chunk_type", "variant", name="uq_product_chunk"),
        CheckConstraint(f"chunk_type IN {CHUNK_TYPES}", name="ck_chunk_type"),
        Index("ix_product_image_embeddings_sku", "sku"),
        Index("ix_product_image_embeddings_meta", "metadata", postgresql_using="gin"),
        # No vector index: ~100 rows scan in milliseconds, and HNSW on `vector`
        # is capped at 2000 dims (< 2048). Use halfvec(2048) if an index is needed.
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64))
    chunk_type: Mapped[str] = mapped_column(String(16))
    variant: Mapped[int] = mapped_column(SmallInteger, default=0)
    content: Mapped[str] = mapped_column(Text)  # image path (relative to catalog dir) or caption text
    content_hash: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[list[float]] = mapped_column(Vector(IMAGE_EMBED_DIM))
    embed_model: Mapped[str] = mapped_column(String(128))
    # "metadata" is reserved on declarative classes → attribute name `meta`
    meta: Mapped[dict] = mapped_column("metadata", JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
