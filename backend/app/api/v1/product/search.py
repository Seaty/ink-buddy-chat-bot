"""POST /api/v1/product-search/by-image — find catalog products in an attached photo."""

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.deps import get_principal
from app.api.policy import access_policy
from app.core.errors import ErrorResponse
from app.core.rate_limit import limiter
from app.core.security import Principal
from app.db.database import get_db
from app.schemas.product import (
    ProductSearchByImageRequest,
    ProductSearchByImageResponse,
)
from app.services.vision_service import VisionService, get_vision_service

router = APIRouter(prefix="/product-search", tags=["product search"])


@router.post(
    "/by-image",
    response_model=ProductSearchByImageResponse,
    responses={s: {"model": ErrorResponse} for s in (401, 404, 422, 503)},
)
@access_policy("guest_or_user")
@limiter.limit("20/minute")
async def search_by_image(
    request: Request,
    response: Response,
    body: ProductSearchByImageRequest,
    principal: Principal = Depends(get_principal),
    service: VisionService = Depends(get_vision_service),
    db: Session = Depends(get_db),
) -> ProductSearchByImageResponse:
    """``exact`` only when the model text read off the photo identifies one product; everything else is
    ``similar``. No match → ``suggestions`` ("did you mean?"). Another principal's image answers 404."""
    return await run_in_threadpool(
        service.search_by_image, db, principal, body.image_id, body.limit
    )
