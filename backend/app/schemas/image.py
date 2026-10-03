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
