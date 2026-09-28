"""Image RAG endpoints: /api/vision."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from ai.llm.ollama_client import OllamaError
from ai.llm.qwen_vision import VisionModelError
from ai.rag.indexing_service import CatalogError
from ai.vision.vision_pipeline import InvalidImageError
from core.config import Settings, get_settings
from core.database import get_db
from schemas.vision import ErrorResponse, IndexCatalogResponse, VisionSearchResponse
from services.vision_service import VisionService, get_vision_service

router = APIRouter(prefix="/api/vision", tags=["vision"])


@router.post(
    "/search",
    response_model=VisionSearchResponse,
    responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def search(
    image: Annotated[UploadFile, File(description="Customer photo (JPEG / PNG / WEBP, ≤ 5 MB)")],
    message: Annotated[str | None, Form(description="Optional question about the photo")] = None,
    service: VisionService = Depends(get_vision_service),
    settings: Settings = Depends(get_settings),
) -> VisionSearchResponse:
    """Find catalog products matching a photo and answer the customer's question."""
    if message and len(message) > settings.image_message_max_chars:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"message longer than {settings.image_message_max_chars} chars")
    data = await image.read(settings.image_max_bytes + 1)  # never buffer more than the limit
    if len(data) > settings.image_max_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "image too large")
    try:
        return await run_in_threadpool(service.search, data, message)
    except InvalidImageError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    except (OllamaError, VisionModelError) as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"vision model unavailable: {e}") from e


@router.post(
    "/index",
    response_model=IndexCatalogResponse,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def index_catalog(
    service: VisionService = Depends(get_vision_service),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> IndexCatalogResponse:
    """(Re)build catalog embeddings in pgvector. Admin only.

    TODO: require an admin user via core/security.py; until then it is off
    unless VISION_ADMIN_ENABLED=true.
    """
    if not settings.vision_admin_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    try:
        return await run_in_threadpool(service.index_catalog, db)
    except CatalogError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
