from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)


class GuestSessionResponse(BaseModel):
    id: UUID
    expires_at: datetime
    image_upload_limit: Literal[3] = 3
    image_uploads_used: int = Field(ge=0, le=3)
    image_uploads_remaining: int = Field(ge=0, le=3)


class GuestClaimResponse(BaseModel):
    guest_session_id: UUID
    user_id: UUID
    chat_sessions_claimed: int = Field(ge=0)
    images_claimed: int = Field(ge=0)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=12, max_length=1024)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("display_name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(max_length=320)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=43, max_length=128)
    password: str = Field(min_length=12, max_length=1024)


class AuthMessageResponse(BaseModel):
    message: str
