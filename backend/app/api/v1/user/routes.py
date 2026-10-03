from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Query
from app.api.scaffold import SCAFFOLD_OPENAPI, SCAFFOLD_RESPONSES, not_implemented
from app.schemas.user import UserProfileResponse, UpdateProfileRequest
router = APIRouter(prefix="/users", tags=["user"])


@router.get("/me", status_code=200, response_model=UserProfileResponse, responses=SCAFFOLD_RESPONSES, openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] get profile", description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.")
def get_profile():
    not_implemented("get_profile")


@router.patch("/me", status_code=200, response_model=UserProfileResponse, responses=SCAFFOLD_RESPONSES, openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] update profile", description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.")
def update_profile(body: UpdateProfileRequest):
    not_implemented("update_profile")
