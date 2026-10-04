from __future__ import annotations

from datetime import datetime
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
    content: str = Field(
        default="",
        max_length=4000,
        description="Proposed MVP limit, pending policy confirmation",
    )
    image_id: UUID | None = None

    @model_validator(mode="after")
    def require_content_or_image(self):
        if not self.content.strip() and self.image_id is None:
            raise ValueError("content or image_id is required")
        return self


class MessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    sequence_number: int = Field(gt=0)
    role: Literal["user", "assistant", "system"]
    content: str
    image_id: UUID | None = None
    product_refs: list[dict] | None = None
    created_at: datetime


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    next_cursor: str | None = None


class SendMessageResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
