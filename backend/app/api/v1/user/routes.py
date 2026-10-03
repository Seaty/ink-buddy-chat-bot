from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_principal
from app.api.policy import access_policy
from app.api.scaffold import SCAFFOLD_OPENAPI, SCAFFOLD_RESPONSES, not_implemented
from app.core.security import Principal
from app.db.database import get_db
from app.schemas.user import UpdateProfileRequest, UserProfileResponse

router = APIRouter(prefix="/users", tags=["user"])


@router.get("/me", response_model=UserProfileResponse)
@access_policy("user")
def get_profile(
    response: Response,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    row = (
        db.execute(
            text(
                "SELECT u.id,u.email,u.display_name,r.name AS role FROM users u JOIN roles r ON r.id=u.role_id WHERE u.id=:id"
            ),
            {"id": principal.id},
        )
        .mappings()
        .one()
    )
    return UserProfileResponse(**row)


@router.patch(
    "/me",
    status_code=200,
    response_model=UserProfileResponse,
    responses=SCAFFOLD_RESPONSES,
    openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] update profile",
    description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.",
)
@access_policy("user")
def update_profile(body: UpdateProfileRequest):
    not_implemented("update_profile")
