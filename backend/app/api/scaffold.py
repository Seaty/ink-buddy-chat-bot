"""Temporary endpoint declarations. Remove when each feature is implemented."""
from app.core.errors import ApiError, ErrorResponse

SCAFFOLD_RESPONSES = {
    501: {"model": ErrorResponse, "description": "Route scaffold only; business logic not implemented"},
    422: {"model": ErrorResponse, "description": "Request validation failed"},
}
SCAFFOLD_OPENAPI = {"x-implementation-status": "scaffold"}

def not_implemented(feature: str) -> None:
    raise ApiError(501, "NOT_IMPLEMENTED", "This endpoint is a scaffold; implementation is pending", {"feature": feature})
