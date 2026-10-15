from __future__ import annotations
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

class TextValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=100)

class TextIndexRequest(TextValidateRequest):
    limit: int = Field(default=5, ge=1, le=100)

class TextIssue(BaseModel):
    product_id: UUID
    field: str
    code: str

class TextValidateResponse(BaseModel):
    examined: int
    valid: int
    invalid: int
    errors: list[TextIssue]
    warnings: list[TextIssue]

class TextIndexResponse(BaseModel):
    examined: int = 0
    indexed: int = 0
    unchanged: int = 0
    invalid: int = 0
    failed: int = 0
    remaining: int = 0
    warnings: list[TextIssue] = Field(default_factory=list)
    errors: list[TextIssue] = Field(default_factory=list)
    seconds: float = 0

class IndexCatalogResponse(BaseModel):
    products: int
    chunks_embedded: int
    chunks_unchanged: int
    chunks_deleted: int
    warnings: list[str] = []
    seconds: float
