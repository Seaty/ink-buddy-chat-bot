"""API schemas for /api/vision (IMAGE_RAG_DESIGN.md §3.6)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ProductCard(BaseModel):
    """Shown by the frontend as a card — values come from catalog data, never from the LLM."""

    sku: str
    name: str
    category: str
    category_th: str
    brand: str
    price_thb: float
    unit: str | None = None
    pack_qty: int | None = None
    unit_price: float | None = None
    price_date: str
    stock_qty: int | None = None
    image_url: str
    source_url: str
    score: float = Field(description="Retrieval score 0-1")


class ImageAnalysisOut(BaseModel):
    is_stationery: bool
    category_guess: str
    brand_text: str = ""
    model_text: str = ""
    colors: list[str] = []
    description: str = ""


class VisionSearchResponse(BaseModel):
    answer: str
    intent: str = Field(description="find_similar | recommend | compare | price_stock | general | out_of_scope")
    match_level: str = Field(description="exact | similar | none")
    products: list[ProductCard] = []
    needs_confirmation: bool = Field(False, description="True → ask the customer which product they mean")
    analysis: ImageAnalysisOut | None = None
    timings_s: dict[str, float] = {}
    path: str = Field("full", description="fast = answered from retrieval only (no VLM); full = VLM used")


class IndexCatalogResponse(BaseModel):
    products: int
    chunks_embedded: int
    chunks_unchanged: int
    chunks_deleted: int
    warnings: list[str] = []
    seconds: float


class ErrorResponse(BaseModel):
    detail: str
