from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Query
from app.api.scaffold import SCAFFOLD_OPENAPI, SCAFFOLD_RESPONSES, not_implemented
from app.schemas.auth import LoginRequest, TokenResponse, GuestSessionResponse, GuestClaimResponse
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", status_code=200, response_model=TokenResponse, responses=SCAFFOLD_RESPONSES, openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] login", description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.")
def login(body: LoginRequest):
    not_implemented("login")


@router.post("/refresh", status_code=200, response_model=TokenResponse, responses=SCAFFOLD_RESPONSES, openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] refresh token", description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.")
def refresh_token():
    not_implemented("refresh_token")


@router.post("/logout", status_code=204, responses=SCAFFOLD_RESPONSES, openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] logout", description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.")
def logout():
    not_implemented("logout")


@router.post("/guest-sessions", status_code=201, response_model=GuestSessionResponse, responses=SCAFFOLD_RESPONSES, openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] create guest session", description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.")
def create_guest_session():
    not_implemented("create_guest_session")


@router.get("/guest-sessions/current", status_code=200, response_model=GuestSessionResponse, responses=SCAFFOLD_RESPONSES, openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] get guest session", description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.")
def get_guest_session():
    not_implemented("get_guest_session")


@router.post("/guest-sessions/current/claim", status_code=200, response_model=GuestClaimResponse, responses=SCAFFOLD_RESPONSES, openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] claim guest session", description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.")
def claim_guest_session():
    not_implemented("claim_guest_session")
