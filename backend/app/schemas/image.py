from __future__ import annotations
from typing import Literal
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field

class ImageUploadResponse(BaseModel):
    id: UUID
    status: str = Field(description="ready | processing | failed")


class ImageDetailResponse(ImageUploadResponse):
    mime_type: str
    size_bytes: int
    created_at: datetime


class ImageAttributes(BaseModel):
    is_stationery: bool
    category: str = Field(description="closest catalog category, or 'other'")
    brand_text: str = Field(description="brand text read off the item; empty if none")
    model_text: str = Field(description="model/series text read off the item; empty if none")
    colors: list[str] = []
    features: list[str] = Field([], description="visible features: tip size, pack count, shape, material")


class ImageAnalysisResponse(BaseModel):
    """An interpretation of the photo, not a confirmed product."""

    image_id: UUID
    description: str
    attributes: ImageAttributes
    cached: bool = Field(description="true = stored result from an earlier analysis of this image")


class OcrSegmentOut(BaseModel):
    text: str


class ImageOcrResponse(BaseModel):
    """Approximate; verify before citing a model or SKU."""

    image_id: UUID
    text: str = Field(description="all segments joined by newlines; empty when no text was found")
    segments: list[OcrSegmentOut]
    cached: bool
