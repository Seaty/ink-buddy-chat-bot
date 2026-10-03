from __future__ import annotations
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"

class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    dependencies: dict[str, str]
