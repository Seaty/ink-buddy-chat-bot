from __future__ import annotations
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

class UserProfileResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None = None
    role: str

class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
