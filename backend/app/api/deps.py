"""Default-deny policy; client-supplied owner IDs are not credentials."""

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.security import Principal, unauthorized
from app.db.database import get_db
from app.services.auth.service import AuthService

GUEST_COOKIE = "ink_buddy_guest"
REFRESH_COOKIE = "ink_buddy_refresh"
POLICIES = {"public", "refresh", "guest", "guest_or_user", "user", "claim", "admin"}


def require_origin(request: Request, settings: Settings):
    if request.headers.get("origin") not in settings.cors_origins:
        raise ApiError(
            403, "ORIGIN_NOT_ALLOWED", "an allowed Origin header is required"
        )


def authorize(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    policy = (getattr(request.scope.get("route"), "openapi_extra", None) or {}).get(
        "x-access-policy"
    )
    if policy not in POLICIES:
        raise ApiError(403, "ACCESS_POLICY_MISSING", "route access is not configured")
    if policy == "public":
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            require_origin(request, settings)
        return None
    if policy == "refresh":
        require_origin(request, settings)
        if not request.cookies.get(REFRESH_COOKIE):
            raise unauthorized()
        return None
    auth = AuthService(db, settings)
    authorization = request.headers.get("authorization")
    if policy == "guest":
        principal = auth.authenticate_guest(request.cookies.get(GUEST_COOKIE))
    elif authorization is not None:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise unauthorized()
        principal = auth.authenticate_user(token)
    elif policy == "guest_or_user":
        principal = auth.authenticate_guest(request.cookies.get(GUEST_COOKIE))
    else:
        raise unauthorized()
    if policy in ("user", "admin", "claim") and principal.kind != "user":
        raise ApiError(403, "FORBIDDEN", "user authentication required")
    if policy == "admin" and principal.role != "admin":
        raise ApiError(403, "FORBIDDEN", "admin role required")
    if policy == "claim":
        auth.authenticate_guest(request.cookies.get(GUEST_COOKIE))
        require_origin(request, settings)
    if principal.kind == "guest" and request.method not in ("GET", "HEAD", "OPTIONS"):
        require_origin(request, settings)
    request.state.principal = principal
    return principal


def get_principal(principal: Principal = Depends(authorize)) -> Principal:
    if principal is None:
        raise unauthorized()
    return principal


def get_current_user_id(principal: Principal = Depends(get_principal)):
    if principal.kind != "user":
        raise ApiError(403, "FORBIDDEN", "user authentication required")
    return principal.id
