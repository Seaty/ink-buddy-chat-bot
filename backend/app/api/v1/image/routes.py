"""/api/v1/images — attach a photo, analyse it, read its text (get/delete are scaffolds)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.deps import get_principal
from app.api.policy import access_policy
from app.api.scaffold import SCAFFOLD_OPENAPI, SCAFFOLD_RESPONSES, not_implemented
from app.core.config import Settings, get_settings
from app.core.errors import ApiError, ErrorResponse
from app.core.security import Principal
from app.db.database import get_db
from app.schemas.image import (
    ImageAnalysisResponse,
    ImageDetailResponse,
    ImageOcrResponse,
    ImageUploadResponse,
)
from app.services.vision_service import VisionService, get_vision_service

router = APIRouter(prefix="/images", tags=["images"])


@router.post(
    "",
    status_code=201,
    response_model=ImageUploadResponse,
    responses={s: {"model": ErrorResponse} for s in (401, 403, 413, 415, 422)},
)
@access_policy("guest_or_user")
async def upload_image(
    file: Annotated[
        UploadFile, File(description="JPEG / PNG / WEBP, checked by content")
    ],
    principal: Principal = Depends(get_principal),
    service: VisionService = Depends(get_vision_service),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> ImageUploadResponse:
    """Attaching a photo does not identify a product yet; call /product-search/by-image next."""
    data = await file.read(
        settings.image_max_bytes + 1
    )  # never buffer more than the limit
    if len(data) > settings.image_max_bytes:
        raise ApiError(
            413,
            "IMAGE_TOO_LARGE",
            f"image larger than {settings.image_max_bytes // (1024 * 1024)} MB",
        )
    return await run_in_threadpool(service.upload_image, db, principal, data)


@router.post(
    "/{image_id}/analysis",
    response_model=ImageAnalysisResponse,
    responses={s: {"model": ErrorResponse} for s in (401, 403, 404, 422, 503)},
)
@access_policy("guest_or_user")
async def analyze_image(
    image_id: UUID,
    principal: Principal = Depends(get_principal),
    service: VisionService = Depends(get_vision_service),
    db: Session = Depends(get_db),
) -> ImageAnalysisResponse:
    """Describe the photo and its visible attributes. An interpretation, not a confirmed product.

    The first call runs the vision model (slow); later calls return the stored result.
    Another principal's image answers 404.
    """
    return await run_in_threadpool(service.analyze_image, db, principal, image_id)


@router.post(
    "/{image_id}/ocr",
    response_model=ImageOcrResponse,
    responses={s: {"model": ErrorResponse} for s in (401, 403, 404, 422, 503)},
)
@access_policy("guest_or_user")
async def ocr_image(
    image_id: UUID,
    principal: Principal = Depends(get_principal),
    service: VisionService = Depends(get_vision_service),
    db: Session = Depends(get_db),
) -> ImageOcrResponse:
    """Read the text printed on the item. Approximate: verify before citing a model or SKU.

    The first call runs the vision model (slow); later calls return the stored result.
    Another principal's image answers 404.
    """
    return await run_in_threadpool(service.ocr_image, db, principal, image_id)


@router.get(
    "/{image_id}",
    status_code=200,
    response_model=ImageDetailResponse,
    responses=SCAFFOLD_RESPONSES,
    openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] get image",
    description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.",
)
@access_policy("guest_or_user")
def get_image(image_id: UUID):
    not_implemented("get_image")


@router.delete(
    "/{image_id}",
    status_code=204,
    responses=SCAFFOLD_RESPONSES,
    openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] delete image",
    description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.",
)
@access_policy("guest_or_user")
def delete_image(image_id: UUID):
    not_implemented("delete_image")
