"""Admin-only indexing endpoints, each protected by its own feature flag."""

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

from app.db.database import get_engine
from app.schemas.admin import TextValidateRequest, TextIndexRequest, TextValidateResponse, TextIndexResponse
from app.services.product.text_index import TextIndexService

def text_index_service(settings: Settings = Depends(get_settings)):
    if not settings.text_index_admin_enabled:
        raise ApiError(404, "NOT_FOUND", "not found")
    return TextIndexService(get_engine(), settings)

@router.post('/text-index/validate', response_model=TextValidateResponse,
             responses={s: {'model': ErrorResponse} for s in (401,403,404,422)})
@access_policy('admin')
def validate_text_catalog(body: TextValidateRequest, service=Depends(text_index_service)):
    return service.validate(body)

@router.post('/text-index', response_model=TextIndexResponse,
             responses={s: {'model': ErrorResponse} for s in (401,403,404,409,422)})
@access_policy('admin')
def index_text_catalog(body: TextIndexRequest, service=Depends(text_index_service)):
    return service.index(body)


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

    Requires an authenticated admin and the image-index feature flag.
    """
    if not settings.vision_admin_enabled:
        raise ApiError(404, "NOT_FOUND", "not found")
    try:
        return await run_in_threadpool(service.index_catalog, db)
    except CatalogError as e:
        raise ApiError(
            422, "CATALOG_INVALID", "catalog metadata has errors", {"report": str(e)}
        ) from e
