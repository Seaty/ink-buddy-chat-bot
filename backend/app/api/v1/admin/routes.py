"""Admin endpoints for the image index. Off unless VISION_ADMIN_ENABLED=true (no admin auth yet)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.ai.rag.indexing_service import CatalogError
from app.api.policy import access_policy
from app.core.config import Settings, get_settings
from app.core.errors import ApiError, ErrorResponse
from app.db.database import get_db
from app.schemas.admin import IndexCatalogResponse
from app.services.vision_service import VisionService, get_vision_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post(
    "/image-index",
    response_model=IndexCatalogResponse,
    responses={s: {"model": ErrorResponse} for s in (404, 422)},
)
@access_policy("admin")
async def rebuild_image_index(
    service: VisionService = Depends(get_vision_service),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> IndexCatalogResponse:
    """(Re)build catalog image embeddings; unchanged items are skipped.

    TODO: require an admin user once core/security.py exists.
    """
    if not settings.vision_admin_enabled:
        raise ApiError(404, "NOT_FOUND", "not found")
    try:
        return await run_in_threadpool(service.index_catalog, db)
    except CatalogError as e:
        raise ApiError(
            422, "CATALOG_INVALID", "catalog metadata has errors", {"report": str(e)}
        ) from e
