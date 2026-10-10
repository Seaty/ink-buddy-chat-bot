from __future__ import annotations
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

MAX_IMAGE_SEARCH_LIMIT = 10

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
    match_type: Literal["exact", "similar", "suggestion"]
    score: float = Field(description="retrieval score 0-1")


class ProductSearchByImageResponse(BaseModel):
    image_id: UUID
    description: str | None = Field(description="the vision model's reading of the photo; null on the fast path")
    match_level: Literal["exact", "similar", "none"]
    matches: list[ProductMatch]
    path: Literal["fast", "full"] = Field(description="fast = embedding search only; full = vision model used")
    suggestions: list[ProductMatch] = Field(
        [], description="only when match_level is none: nearest products to offer as 'did you mean?'"
    )
    message: str | None = Field(None, description="customer-facing text when nothing matched (did-you-mean)")
    timings_s: dict[str, float] = {}


class ProductResponse(BaseModel):
    id: UUID
    sku: str | None = None
    name: str
    category: str | None = None
    brand: str | None = None
    description: str | None = None
    price: float | None = None
    currency: str | None = None
    availability: str | None = None
    source_ref: str | None = None

class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    next_cursor: str | None = None
