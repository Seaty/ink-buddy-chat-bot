"""POST /api/v1/product-search/by-image — find catalog products in an attached photo."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.core.errors import ErrorResponse
from app.db.database import get_db
from app.schemas.product import ProductSearchByImageRequest, ProductSearchByImageResponse
from app.services.vision_service import VisionService, get_vision_service

router = APIRouter(prefix="/product-search", tags=["product search"])


@router.post(
    "/by-image",
    response_model=ProductSearchByImageResponse,
    responses={s: {"model": ErrorResponse} for s in (401, 404, 422, 503)},
)
async def search_by_image(
    body: ProductSearchByImageRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: VisionService = Depends(get_vision_service),
    db: Session = Depends(get_db),
) -> ProductSearchByImageResponse:
    """``exact`` only when the model text read off the photo identifies one product; everything else is ``similar``."""
    return await run_in_threadpool(service.search_by_image, db, user_id, body.image_id, body.limit)
