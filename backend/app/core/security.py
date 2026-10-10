"""Credential primitives. Tokens and passwords must never be logged."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from uuid import UUID

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from jose import JWTError, jwt

from app.core.config import Settings
from app.core.errors import ApiError

password_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def unauthorized() -> ApiError:
    return ApiError(401, "UNAUTHORIZED", "invalid or expired credentials")


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    return hash_password(new_token())


def verify_password(password: str, stored: str) -> bool:
    try:
        if stored.startswith(("$2a$", "$2b$", "$2y$")):
            # Historical bcrypt truncates at 72 bytes; preserve verification semantics.
            return bcrypt.checkpw(password.encode()[:72], stored.encode())
        return password_hasher.verify(stored, password)
    except (VerificationError, InvalidHashError, ValueError):
        return False


def needs_password_upgrade(stored: str) -> bool:
    return not stored.startswith("$argon2id$") or password_hasher.check_needs_rehash(
        stored
    )


@dataclass(frozen=True)
class Principal:
    kind: str
    id: UUID
    role: str | None = None
    session_id: UUID | None = None
    access_expires_at: datetime | None = None


def access_token(
    settings: Settings, user_id: UUID, session_id: UUID, session_expiry: datetime
) -> tuple[str, int]:
    now = utcnow()
    expiry = min(now + timedelta(seconds=settings.auth_access_seconds), session_expiry)
    seconds = max(1, int((expiry - now).total_seconds()))
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "iss": settings.auth_jwt_issuer,
        "aud": settings.auth_jwt_audience,
        "iat": now,
        "exp": expiry,
        "type": "access",
    }
    return jwt.encode(payload, settings.auth_jwt_secret, algorithm="HS256"), seconds


def decode_access(settings: Settings, token: str) -> tuple[UUID, UUID]:
    try:
        claims = jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=["HS256"],
            issuer=settings.auth_jwt_issuer,
            audience=settings.auth_jwt_audience,
            options={
                "require_exp": True,
                "require_iat": True,
                "require_sub": True,
                "require_aud": True,
                "require_iss": True,
            },
        )
        if claims.get("type") != "access":
            raise ValueError("wrong token type")
        return UUID(claims["sub"]), UUID(claims["sid"])
    except (JWTError, ValueError, KeyError, TypeError):
        raise unauthorized() from None
