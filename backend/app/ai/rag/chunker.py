"""Chunking.

Image RAG part: turn catalog products into retrieval units
(IMAGE_RAG_DESIGN.md §2.2). Price, stock and price date are deliberately
left out of chunk content — they change often and are read live from metadata.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from .indexing_service import CatalogProduct

CAPTION_TEMPLATE = (
    "{name}\n"
    "ประเภท: {category_th} ({category}) | กลุ่ม: {group}\n"
    "แบรนด์: {brand}"
)


@dataclass(frozen=True)
class CatalogChunk:
    sku: str
    chunk_type: str  # "image" | "caption"
    variant: int
    content: str  # image path relative to the catalog dir, or caption text
    content_hash: str
    metadata: dict


def build_caption(p: CatalogProduct) -> str:
    text = CAPTION_TEMPLATE.format(
        name=p.name, category_th=p.category_th, category=p.category, group=p.group, brand=p.brand_norm,
    )
    details = " | ".join(f"{label}: {value}" for label, value in (("สี", p.color), ("ขนาด", p.size)) if value)
    if details:
        text += f"\n{details}"
    if p.visual_caption:
        text += f"\nลักษณะ: {p.visual_caption}"
    return text


def build_catalog_chunks(products: Iterable[CatalogProduct]) -> list[CatalogChunk]:
    """One ``image`` and one ``caption`` chunk per active product.

    ``content_hash`` lets indexing skip re-embedding unchanged chunks.
    """
    chunks = []
    for p in products:
        if not p.is_active:
            continue
        meta = p.to_metadata()
        chunks.append(CatalogChunk(
            sku=p.sku,
            chunk_type="image",
            variant=0,
            content=p.filename,
            content_hash=hashlib.sha256(p.image_path.read_bytes()).hexdigest(),
            metadata=meta,
        ))
        caption = build_caption(p)
        chunks.append(CatalogChunk(
            sku=p.sku,
            chunk_type="caption",
            variant=0,
            content=caption,
            content_hash=hashlib.sha256(caption.encode("utf-8")).hexdigest(),
            metadata=meta,
        ))
    return chunks
