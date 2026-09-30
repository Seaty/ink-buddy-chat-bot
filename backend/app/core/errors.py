"""API error format (docs/architecture/INK_BUDDY_DESIGN_DRAFT.md §3 Conventions).

Every error response is ``{"error": {"code", "message", "details"}}``.
Raise ``ApiError`` from services/routes; FastAPI's own HTTP and validation
errors are converted by the handlers installed in ``install_error_handlers``.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    503: "SERVICE_UNAVAILABLE",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details or {}


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorResponse(BaseModel):
    """For OpenAPI ``responses=`` declarations."""

    error: ErrorBody


def error_response(status: int, code: str, message: str, details: dict | None = None, headers=None) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "details": details or {}}}
    return JSONResponse(status_code=status, content=jsonable_encoder(body), headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, e: ApiError):
        return error_response(e.status, e.code, e.message, e.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, e: StarletteHTTPException):
        code = STATUS_CODES.get(e.status_code, f"HTTP_{e.status_code}")
        message = e.detail if isinstance(e.detail, str) else code.replace("_", " ").lower()
        return error_response(e.status_code, code, message, headers=getattr(e, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, e: RequestValidationError):
        # drop "input"/"ctx": they can echo user data or hold non-JSON objects
        fields = [{"loc": list(err.get("loc", ())), "msg": err.get("msg"), "type": err.get("type")} for err in e.errors()]
        return error_response(422, "VALIDATION_ERROR", "request validation failed", {"errors": fields})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, e: Exception):
        logger.exception("unhandled error")
        return error_response(500, "INTERNAL_ERROR", "internal server error")
