from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


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
    content: str = Field(min_length=1, max_length=4000)
    client_request_id: UUID

    @field_validator("content", mode="before")
    @classmethod
    def trim_content(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("client_request_id")
    @classmethod
    def request_v7(cls, value):
        if value.version != 7:
            raise ValueError("client_request_id must be UUIDv7")
        return value


class ProductReference(BaseModel):
    id: UUID
    sku: str | None = None
    name: str
    price: Decimal | None = None
    currency: str | None = None
    availability: str | None = None
    source_ref: str | None = None


class MessageResponse(BaseModel):
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
