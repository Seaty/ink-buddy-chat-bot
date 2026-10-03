from __future__ import annotations
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

class IndexCatalogResponse(BaseModel):
    products: int
    chunks_embedded: int
    chunks_unchanged: int
    chunks_deleted: int
    warnings: list[str] = []
    seconds: float
