"""Transactional auth lifecycle; parent session locks serialize refresh/logout."""

from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.password_policy import validate_new_password
from app.core.security import (
    Principal,
    access_token,
    decode_access,
    dummy_password_hash,
    hash_password,
    needs_password_upgrade,
    new_token,
    token_hash,
    unauthorized,
    utcnow,
    verify_password,
)
from app.repositories.auth.repository import AuthRepository
from app.schemas.auth import GuestClaimResponse, GuestSessionResponse, TokenResponse
from app.services.auth.mail import Mailer


def require_live_guest(row):
    if (
        not row
        or row["expires_at"] <= utcnow()
        or row["revoked_at"]
        or row["claimed_at"]
    ):
        raise unauthorized()
    return row


def guest_response(row):
    return GuestSessionResponse(
        id=row["id"],
        expires_at=row["expires_at"],
        image_uploads_used=row["image_uploads_used"],
        image_uploads_remaining=row["image_upload_limit"] - row["image_uploads_used"],
    )


class AuthService:
    def __init__(self, db: Session, settings: Settings):
        self.db, self.settings, self.repo = db, settings, AuthRepository(db)

    def login(self, email: str, password: str):
        user = self.repo.user_by_email(email)
        valid = verify_password(
            password, user["password_hash"] if user else dummy_password_hash()
        )
        if not user or not valid or not user["is_active"]:
            raise unauthorized()
        locked = self.repo.one(
            "SELECT * FROM users WHERE id=:id FOR UPDATE", id=user["id"]
        )
        if not locked["is_active"] or locked["password_hash"] != user["password_hash"]:
            raise unauthorized()
        if needs_password_upgrade(user["password_hash"]):
            self.repo.execute(
                "UPDATE users SET password_hash=:hash,updated_at=now() WHERE id=:id",
                hash=hash_password(password),
                id=user["id"],
            )
        expiry = utcnow() + timedelta(seconds=self.settings.auth_session_seconds)
        parent = self.repo.one(
            "INSERT INTO auth_sessions(user_id,expires_at) VALUES(:uid,:expiry) RETURNING *",
            uid=user["id"],
            expiry=expiry,
        )
        refresh = new_token()
        self.repo.execute(
            "INSERT INTO refresh_tokens(user_id,session_id,token_hash,expires_at) VALUES(:uid,:sid,:hash,:expiry)",
            uid=user["id"],
            sid=parent["id"],
            hash=token_hash(refresh),
            expiry=expiry,
        )
        token, seconds = access_token(self.settings, user["id"], parent["id"], expiry)
        self.db.commit()
        return TokenResponse(access_token=token, expires_in=seconds), refresh, expiry

    def authenticate_user(self, token: str):
        uid, sid = decode_access(self.settings, token)
        user = self.repo.user_session(uid, sid)
        if not user:
            raise unauthorized()
        return Principal("user", uid, user["role"], sid)

    def authenticate_guest(self, token: str | None):
        if not token:
            raise unauthorized()
        row = require_live_guest(self.repo.guest_by_hash(token_hash(token)))
        return Principal("guest", row["id"])

    def refresh(self, raw: str | None):
        if not raw:
            raise unauthorized()
        parent, old = self.repo.lock_refresh_session(token_hash(raw))
        if not parent or not old:
            raise unauthorized()
        if old["rotated_at"]:
            self.repo.revoke_session(parent["id"])
            self.db.commit()  # Persist reuse revocation despite the error response.
            raise unauthorized()
        if (
            old["revoked_at"]
            or parent["revoked_at"]
            or min(old["expires_at"], parent["expires_at"]) <= utcnow()
        ):
            raise unauthorized()
        if not self.repo.user_session(parent["user_id"], parent["id"]):
            self.repo.revoke_session(parent["id"])
            self.db.commit()
            raise unauthorized()
        raw_new = new_token()
        replacement = self.repo.one(
            "INSERT INTO refresh_tokens(user_id,session_id,token_hash,expires_at) VALUES(:uid,:sid,:hash,:expiry) RETURNING id",
            uid=parent["user_id"],
            sid=parent["id"],
            hash=token_hash(raw_new),
            expiry=parent["expires_at"],
        )
        self.repo.execute(
            "UPDATE refresh_tokens SET rotated_at=now(),revoked_at=now(),replaced_by_id=:replacement WHERE id=:id",
            replacement=replacement["id"],
            id=old["id"],
        )
        token, seconds = access_token(
            self.settings, parent["user_id"], parent["id"], parent["expires_at"]
        )
        self.db.commit()
        return (
            TokenResponse(access_token=token, expires_in=seconds),
            raw_new,
            parent["expires_at"],
        )

    def logout(self, raw: str | None):
        if not raw:
            raise unauthorized()
        parent, old = self.repo.lock_refresh_session(token_hash(raw))
        if not parent or not old:
            raise unauthorized()
        self.repo.revoke_session(parent["id"])
        self.db.commit()

    def create_guest(self, raw: str | None):
        if raw:
            row = self.repo.guest_by_hash(token_hash(raw), lock=True)
            if (
                row
                and row["expires_at"] > utcnow()
                and not row["revoked_at"]
                and not row["claimed_at"]
            ):
                return guest_response(row), raw, False
        raw = new_token()
        row = self.repo.one(
            "INSERT INTO guest_sessions(token_hash,expires_at) VALUES(:hash,:expiry) RETURNING *",
            hash=token_hash(raw),
            expiry=utcnow() + timedelta(seconds=self.settings.auth_guest_seconds),
        )
        self.db.commit()
        return guest_response(row), raw, True

    def current_guest(self, raw: str | None):
        if not raw:
            raise unauthorized()
        return guest_response(
            require_live_guest(self.repo.guest_by_hash(token_hash(raw)))
        )

    def claim(self, user: Principal, raw_guest: str):
        row = require_live_guest(
            self.repo.guest_by_hash(token_hash(raw_guest), lock=True)
        )
        chats = self.repo.execute(
            "UPDATE chat_sessions SET user_id=:uid,guest_session_id=NULL,updated_at=now() WHERE guest_session_id=:gid",
            uid=user.id,
            gid=row["id"],
        ).rowcount
        images = self.repo.execute(
            "UPDATE image_uploads SET user_id=:uid,guest_session_id=NULL WHERE guest_session_id=:gid",
            uid=user.id,
            gid=row["id"],
        ).rowcount
        self.repo.execute(
            "UPDATE guest_sessions SET claimed_by_user_id=:uid,claimed_at=now(),revoked_at=now() WHERE id=:gid",
            uid=user.id,
            gid=row["id"],
        )
        self.db.commit()
        return GuestClaimResponse(
            guest_session_id=row["id"],
            user_id=user.id,
            chat_sessions_claimed=chats,
            images_claimed=images,
        )

    def register(self, email, password, display_name):
        validate_new_password(password)
        hashed = hash_password(password)
        try:
            role = self.repo.one("SELECT id FROM roles WHERE name='user'")
            if not role:
                raise ApiError(
                    503, "AUTH_CONFIGURATION_ERROR", "registration unavailable"
                )
            self.repo.execute(
                "INSERT INTO users(role_id,email,password_hash,display_name) VALUES(:role,:email,:hash,:name)",
                role=role["id"],
                email=email.lower(),
                hash=hashed,
                name=display_name,
            )
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            if getattr(error.orig, "sqlstate", None) == "23505":
                raise ApiError(
                    409, "EMAIL_ALREADY_REGISTERED", "email already registered"
                ) from None
            raise

    def forgot_password(self, email):
        user = self.repo.one(
            "SELECT * FROM users WHERE lower(email)=lower(:email) FOR UPDATE",
            email=email,
        )
        if not user or not user["is_active"]:
            return None
        recent = self.repo.one(
            "SELECT id FROM password_reset_tokens WHERE user_id=:uid AND created_at > clock_timestamp()-(:seconds * interval '1 second') LIMIT 1",
            uid=user["id"],
            seconds=self.settings.auth_reset_cooldown_seconds,
        )
        if recent:
            return None
        raw = new_token()
        self.repo.execute(
            "UPDATE password_reset_tokens SET revoked_at=clock_timestamp() WHERE user_id=:uid AND used_at IS NULL AND revoked_at IS NULL",
            uid=user["id"],
        )
        self.repo.execute(
            "INSERT INTO password_reset_tokens(user_id,token_hash,expires_at) VALUES(:uid,:hash,:expiry)",
            uid=user["id"],
            hash=token_hash(raw),
            expiry=utcnow() + timedelta(seconds=self.settings.auth_reset_seconds),
        )
        self.db.commit()
        link = (
            self.settings.auth_frontend_url.rstrip("/") + "/reset-password#token=" + raw
        )
        return Mailer(self.settings).message(
            user["email"],
            "Ink Buddy: reset your password",
            "Use this one-time link within "
            + str(self.settings.auth_reset_seconds // 60)
            + " minutes:\n"
            + link
            + "\nIf you did not request this, ignore this email.",
        )

    def reset_password(self, raw, password):
        validate_new_password(password)
        hashed_token = token_hash(raw)
        found = self.repo.one(
            "SELECT user_id FROM password_reset_tokens WHERE token_hash=:hash",
            hash=hashed_token,
        )
        if not found:
            raise ApiError(400, "INVALID_RESET_TOKEN", "invalid or expired reset link")
        user = self.repo.one(
            "SELECT * FROM users WHERE id=:uid FOR UPDATE", uid=found["user_id"]
        )
        token = self.repo.one(
            "SELECT * FROM password_reset_tokens WHERE token_hash=:hash FOR UPDATE",
            hash=hashed_token,
        )
        if (
            not user
            or not user["is_active"]
            or not token
            or token["used_at"]
            or token["revoked_at"]
            or token["expires_at"] <= utcnow()
        ):
            raise ApiError(400, "INVALID_RESET_TOKEN", "invalid or expired reset link")
        self.repo.execute(
            "UPDATE users SET password_hash=:hash,updated_at=clock_timestamp() WHERE id=:uid",
            hash=hash_password(password),
            uid=user["id"],
        )
        # Parent-before-refresh-token order matches refresh/logout; serialize each session.
        self.repo.execute(
            "SELECT id FROM auth_sessions WHERE user_id=:uid ORDER BY id FOR UPDATE",
            uid=user["id"],
        )
        self.repo.execute(
            "UPDATE auth_sessions SET revoked_at=COALESCE(revoked_at,clock_timestamp()) WHERE user_id=:uid",
            uid=user["id"],
        )
        self.repo.execute(
            "UPDATE refresh_tokens SET revoked_at=COALESCE(revoked_at,clock_timestamp()) WHERE user_id=:uid",
            uid=user["id"],
        )
        self.repo.execute(
            "UPDATE password_reset_tokens SET used_at=clock_timestamp() WHERE id=:id",
            id=token["id"],
        )
        self.repo.execute(
            "UPDATE password_reset_tokens SET revoked_at=clock_timestamp() WHERE user_id=:uid AND id<>:id AND used_at IS NULL AND revoked_at IS NULL",
            uid=user["id"],
            id=token["id"],
        )
        self.db.commit()
        return Mailer(self.settings).message(
            user["email"],
            "Ink Buddy: password changed",
            "Your password was changed and existing login sessions were signed out. If you did not make this change, contact your support team.",
        )
