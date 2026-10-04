from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import GUEST_COOKIE, REFRESH_COOKIE, get_principal
from app.api.policy import access_policy
from app.core.config import Settings, get_settings
from app.core.errors import ErrorResponse
from app.core.rate_limit import limiter
from app.core.security import Principal, utcnow
from app.db.database import get_db
from app.schemas.auth import (
    GuestClaimResponse,
    GuestSessionResponse,
    LoginRequest,
    TokenResponse,
)
from app.services.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
ERRORS = {s: {"model": ErrorResponse} for s in (401, 403, 422, 429)}


def set_cookie(
    response: Response, settings: Settings, name: str, raw: str, expiry: datetime
):
    response.set_cookie(
        name,
        raw,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/api/v1",
        expires=expiry.astimezone(timezone.utc),
        max_age=max(0, int((expiry - utcnow()).total_seconds())),
    )
    response.headers["Cache-Control"] = "no-store"


def clear_cookie(response: Response, settings: Settings, name: str):
    response.delete_cookie(
        name,
        path="/api/v1",
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"


@router.post("/login", response_model=TokenResponse, responses=ERRORS)
@limiter.limit("10/minute")
@access_policy("public")
def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    result, refresh, expiry = AuthService(db, settings).login(
        str(body.email), body.password
    )
    set_cookie(response, settings, REFRESH_COOKIE, refresh, expiry)
    return result


@router.post("/refresh", response_model=TokenResponse, responses=ERRORS)
@limiter.limit("30/minute")
@access_policy("refresh")
def refresh_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    result, refresh, expiry = AuthService(db, settings).refresh(
        request.cookies.get(REFRESH_COOKIE)
    )
    set_cookie(response, settings, REFRESH_COOKIE, refresh, expiry)
    return result


@router.post("/logout", status_code=204, responses=ERRORS)
@access_policy("refresh")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    AuthService(db, settings).logout(request.cookies.get(REFRESH_COOKIE))
    clear_cookie(response, settings, REFRESH_COOKIE)


@router.post(
    "/guest-sessions",
    status_code=201,
    response_model=GuestSessionResponse,
    responses={**ERRORS, 200: {"model": GuestSessionResponse}},
)
@limiter.limit("5/hour")
@access_policy("public")
def create_guest_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    result, token, created = AuthService(db, settings).create_guest(
        request.cookies.get(GUEST_COOKIE)
    )
    response.status_code = 201 if created else 200
    set_cookie(response, settings, GUEST_COOKIE, token, result.expires_at)
    return result


@router.get(
    "/guest-sessions/current", response_model=GuestSessionResponse, responses=ERRORS
)
@access_policy("guest")
def get_guest_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    response.headers["Cache-Control"] = "no-store"
    return AuthService(db, settings).current_guest(request.cookies.get(GUEST_COOKIE))


@router.post(
    "/guest-sessions/current/claim", response_model=GuestClaimResponse, responses=ERRORS
)
@access_policy("claim")
def claim_guest_session(
    request: Request,
    response: Response,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    result = AuthService(db, settings).claim(principal, request.cookies[GUEST_COOKIE])
    clear_cookie(response, settings, GUEST_COOKIE)
    return result
