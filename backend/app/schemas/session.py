from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class CreateSessionRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("title", mode="before")
    @classmethod
    def trim_title(cls, value):
        return value.strip() if isinstance(value, str) else value


class RenameSessionRequest(CreateSessionRequest):
    title: str = Field(min_length=1, max_length=200)


class SessionResponse(BaseModel):
    id: UUID
    title: str | None
    summary: str | None = None
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    items: list[SessionResponse]
    next_cursor: str | None = None


class SendMessageRequest(BaseModel):
    model_config = {"extra": "forbid"}
    content: str = Field(default='', max_length=4000)
    image_id: UUID | None = None
    client_request_id: UUID

    @field_validator("content", mode="before")
    @classmethod
    def trim_content(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode='after')
    def content_or_image(self):
        if not self.content and not self.image_id:raise ValueError('content or image_id is required')
        if not self.content:self.content='มีสินค้านี้ไหม'
        if self.image_id and len(self.content)>500:raise ValueError('image prompt must not exceed 500 characters')
        return self

    @field_validator("client_request_id")
    @classmethod
    def request_v7(cls, value):
        if value.version != 7:
            raise ValueError("client_request_id must be UUIDv7")
        return value


class ProductFactReference(BaseModel):
    id: UUID
    sku: str | None = None
    name: str
    price: Decimal | None = None
    currency: str | None = None
    availability: str | None = None
    source_ref: str | None = None
    price_source_ref: str | None = None
    price_basis: str | None = None
    price_verification: str | None = None
    selling_unit: str | None = None
    pack_quantity: int | None = Field(default=None,ge=1)
    ink_color: str | None = None
    body_color: str | None = None


class ProductReference(ProductFactReference):
    variants: list[ProductFactReference] = Field(default_factory=list,max_length=5)
    match_type: Literal['exact','similar','suggestion'] | None = None
    match_score: float | None = Field(default=None,ge=0,le=1,description='Retrieval similarity, not confidence or stock availability')
    match_method: Literal['image_embedding','vision_text_catalog'] | None = None


class MessageResponse(BaseModel):
    model_name: str | None = Field(default=None,max_length=100)
    id: UUID
    session_id: UUID
    sequence_number: int = Field(gt=0)
    role: Literal["user", "assistant", "system"]
    content: str
    image_id: UUID | None = None
    product_refs: list[ProductReference] | None = None
    created_at: datetime


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    next_cursor: str | None = None


class SendMessageResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
