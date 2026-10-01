"""API schemas for images and image-based product search (INK_BUDDY_DESIGN_DRAFT.md §3)."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

MAX_IMAGE_SEARCH_LIMIT = 10


class ImageUploadResponse(BaseModel):
    id: UUID
    status: str = Field(description="ready | processing | failed")


class ProductSearchByImageRequest(BaseModel):
    image_id: UUID
    limit: int = Field(5, ge=1, le=MAX_IMAGE_SEARCH_LIMIT)


class ProductMatch(BaseModel):
    """Catalog facts come from the products table, never from the model."""

    product_id: UUID
    sku: str | None
    name: str
    category: str | None
    brand: str | None
    price: float | None = Field(description="null when the catalog has no price")
    currency: str | None
    availability: str | None = Field(description="null when the catalog has no availability data")
    source_ref: str | None = Field(description="where the product data came from")
    image_url: str | None
    match_type: Literal["exact", "similar"]
    score: float = Field(description="retrieval score 0-1")


class ProductSearchByImageResponse(BaseModel):
    image_id: UUID
    description: str | None = Field(description="the vision model's reading of the photo; null on the fast path")
    match_level: Literal["exact", "similar", "none"]
    matches: list[ProductMatch]
    path: Literal["fast", "full"] = Field(description="fast = embedding search only; full = vision model used")
    timings_s: dict[str, float] = {}


class IndexCatalogResponse(BaseModel):
    products: int
    chunks_embedded: int
    chunks_unchanged: int
    chunks_deleted: int
    warnings: list[str] = []
    seconds: float
