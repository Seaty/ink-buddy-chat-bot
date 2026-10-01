"""Shared API dependencies.

``get_current_user_id`` is a TEMPORARY stand-in until JWT auth exists
(core/security.py). With DEV_AUTH_EMAIL set, every request acts as that user;
otherwise every protected endpoint answers 401. Replace this function with
token verification — callers only rely on it returning the user's UUID.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.database import get_db

_dev_user_ids: dict[str, UUID] = {}


def get_current_user_id(settings: Settings = Depends(get_settings), db: Session = Depends(get_db)) -> UUID:
    email = settings.dev_auth_email
    if not email:
        raise ApiError(401, "UNAUTHORIZED", "authentication required")
    if email not in _dev_user_ids:
        _dev_user_ids[email] = _get_or_create_dev_user(db, email)
    return _dev_user_ids[email]


def _get_or_create_dev_user(db: Session, email: str) -> UUID:
    found = db.execute(text("SELECT id FROM users WHERE lower(email) = lower(:email)"), {"email": email}).scalar()
    if found:
        return found
    # password_hash "!" matches no bcrypt/argon2 hash, so this account can never log in
    user_id = db.execute(
        text(
            "INSERT INTO users (role_id, email, password_hash, display_name) "
            "SELECT id, :email, '!', 'Dev user' FROM roles WHERE name = 'user' RETURNING id"
        ),
        {"email": email},
    ).scalar_one()
    db.commit()
    return user_id
