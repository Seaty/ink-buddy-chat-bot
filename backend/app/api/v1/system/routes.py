from __future__ import annotations

from fastapi import APIRouter

from app.api.policy import access_policy
from app.api.scaffold import SCAFFOLD_OPENAPI, SCAFFOLD_RESPONSES, not_implemented
from app.schemas.system import HealthResponse, ReadinessResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
@access_policy("public")
def health() -> HealthResponse:
    return HealthResponse()


@router.get(
    "/ready",
    status_code=200,
    response_model=ReadinessResponse,
    responses=SCAFFOLD_RESPONSES,
    openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] readiness",
    description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.",
)
@access_policy("admin")
def readiness():
    not_implemented("readiness")
