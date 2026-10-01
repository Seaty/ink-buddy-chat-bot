"""POST /api/v1/images — attach a photo (multipart field ``file``)."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.core.config import Settings, get_settings
from app.core.errors import ApiError, ErrorResponse
from app.db.database import get_db
from app.schemas.vision import ImageAnalysisResponse, ImageOcrResponse, ImageUploadResponse
from app.services.vision_service import VisionService, get_vision_service

router = APIRouter(prefix="/images", tags=["images"])


@router.post(
    "",
    status_code=201,
    response_model=ImageUploadResponse,
    responses={s: {"model": ErrorResponse} for s in (401, 413, 415, 422)},
)
async def upload_image(
    file: Annotated[UploadFile, File(description="JPEG / PNG / WEBP, checked by content")],
    user_id: UUID = Depends(get_current_user_id),
    service: VisionService = Depends(get_vision_service),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> ImageUploadResponse:
    """Attaching a photo does not identify a product yet; call /product-search/by-image next."""
    data = await file.read(settings.image_max_bytes + 1)  # never buffer more than the limit
    if len(data) > settings.image_max_bytes:
        raise ApiError(413, "IMAGE_TOO_LARGE", f"image larger than {settings.image_max_bytes // (1024 * 1024)} MB")
    return await run_in_threadpool(service.upload_image, db, user_id, data)


@router.post(
    "/{image_id}/analysis",
    response_model=ImageAnalysisResponse,
    responses={s: {"model": ErrorResponse} for s in (401, 404, 422, 503)},
)
async def analyze_image(
    image_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: VisionService = Depends(get_vision_service),
    db: Session = Depends(get_db),
) -> ImageAnalysisResponse:
    """Describe the photo and its visible attributes. An interpretation, not a confirmed product.

    The first call runs the vision model (slow); later calls return the stored result.
    """
    return await run_in_threadpool(service.analyze_image, db, user_id, image_id)


@router.post(
    "/{image_id}/ocr",
    response_model=ImageOcrResponse,
    responses={s: {"model": ErrorResponse} for s in (401, 404, 422, 503)},
)
async def ocr_image(
    image_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: VisionService = Depends(get_vision_service),
    db: Session = Depends(get_db),
) -> ImageOcrResponse:
    """Read the text printed on the item. Approximate: verify before citing a model or SKU.

    The first call runs the vision model (slow); later calls return the stored result.
    """
    return await run_in_threadpool(service.ocr_image, db, user_id, image_id)
