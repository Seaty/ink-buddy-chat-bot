"""DDL-owned auth tables. Services own commits and lock ordering."""

from sqlalchemy import text
from sqlalchemy.orm import Session


class AuthRepository:
    def __init__(self, db: Session):
        self.db = db

    def one(self, sql: str, **params):
        return self.db.execute(text(sql), params).mappings().one_or_none()

    def execute(self, sql: str, **params):
        return self.db.execute(text(sql), params)

    def user_by_email(self, email: str):
        return self.one(
            "SELECT u.*, r.name AS role FROM users u JOIN roles r ON r.id=u.role_id WHERE lower(email)=lower(:email)",
            email=email,
        )

    def user_session(self, user_id, session_id):
        return self.one(
            """SELECT u.id, r.name AS role FROM users u JOIN roles r ON r.id=u.role_id
            JOIN auth_sessions a ON a.user_id=u.id WHERE u.id=:uid AND a.id=:sid
            AND u.is_active AND a.revoked_at IS NULL AND a.expires_at>clock_timestamp()""",
            uid=user_id,
            sid=session_id,
        )

    def guest_by_hash(self, hashed: str, lock=False):
        return self.one(
            "SELECT * FROM guest_sessions WHERE token_hash=:hash"
            + (" FOR UPDATE" if lock else ""),
            hash=hashed,
        )

    def lock_guest(self, guest_id):
        return self.one(
            "SELECT * FROM guest_sessions WHERE id=:id FOR UPDATE", id=guest_id
        )

    def lock_refresh_session(self, hashed: str):
        # Lock parent first for all refresh/logout operations; concurrent rotations serialize.
        found = self.one(
            "SELECT session_id FROM refresh_tokens WHERE token_hash=:hash", hash=hashed
        )
        if not found or not found["session_id"]:
            return None, None
        parent = self.one(
            "SELECT * FROM auth_sessions WHERE id=:id FOR UPDATE",
            id=found["session_id"],
        )
        token = self.one(
            "SELECT * FROM refresh_tokens WHERE token_hash=:hash FOR UPDATE",
            hash=hashed,
        )
        return parent, token

    def revoke_session(self, session_id):
        self.execute(
            "UPDATE auth_sessions SET revoked_at=COALESCE(revoked_at, now()) WHERE id=:id",
            id=session_id,
        )
        self.execute(
            "UPDATE refresh_tokens SET revoked_at=COALESCE(revoked_at, now()) WHERE session_id=:id",
            id=session_id,
        )
