"""Owned chat sessions, scoped cursors, and Guest-before-chat lock ordering."""

import base64
import json
from datetime import datetime
from uuid import UUID

from app.core.errors import ApiError
from app.core.security import unauthorized
from app.repositories.auth.repository import AuthRepository
from app.repositories.session.repository import SessionRepository
from app.schemas.session import (
    MessageListResponse,
    MessageResponse,
    SessionListResponse,
    SessionResponse,
)
from app.services.auth.service import require_live_guest


def encode_cursor(value):
    return (
        base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )


def decode_cursor(cursor, kind, owner, session=None):
    if cursor is None:
        return None
    try:
        if len(cursor) > 1024:
            raise ValueError()
        data = json.loads(
            base64.b64decode(
                cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True
            )
        )
        if (
            data["kind"] != kind
            or data["owner"] != str(owner)
            or data.get("session") != session
        ):
            raise ValueError()
        if kind == "sessions":
            timestamp = datetime.fromisoformat(data["time"])
            if timestamp.tzinfo is None:
                raise ValueError()
            return timestamp, UUID(data["id"])
        number = data["sequence"]
        if type(number) is not int or not 0 < number <= 2147483647:
            raise ValueError()
        return number
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise ApiError(422, "INVALID_CURSOR", "invalid pagination cursor") from None


class ChatSessionService:
    def __init__(self, db):
        self.db = db
        self.repo = SessionRepository(db)
        self.auth = AuthRepository(db)

    def authorize(self, principal):
        if principal.kind == "guest":
            require_live_guest(self.auth.lock_guest(principal.id))
        elif not self.auth.user_session(principal.id, principal.session_id):
            raise unauthorized()

    def owned(self, principal, sid, lock=False):
        row = self.repo.get(principal, sid, lock)
        if not row:
            raise ApiError(404, "NOT_FOUND", "chat session not found")
        return row

    def create(self, principal, title):
        self.authorize(principal)
        row = self.repo.create(principal, title or "แชตใหม่")
        self.db.commit()
        return SessionResponse(**row)

    def list(self, principal, limit, cursor):
        self.authorize(principal)
        boundary = decode_cursor(cursor, "sessions", principal.id)
        rows = self.repo.list(principal, limit, boundary)
        items = rows[:limit]
        next_cursor = None
        if len(rows) > limit:
            last = items[-1]
            next_cursor = encode_cursor(
                {
                    "kind": "sessions",
                    "owner": str(principal.id),
                    "time": last["updated_at"].isoformat(),
                    "id": str(last["id"]),
                }
            )
        return SessionListResponse(
            items=[SessionResponse(**r) for r in items], next_cursor=next_cursor
        )

    def get(self, principal, sid):
        self.authorize(principal)
        return SessionResponse(**self.owned(principal, sid))

    def rename(self, principal, sid, title):
        self.authorize(principal)
        self.owned(principal, sid, lock=True)
        row = self.repo.rename(sid, title)
        self.db.commit()
        return SessionResponse(**row)

    def delete(self, principal, sid):
        self.authorize(principal)
        self.owned(principal, sid, lock=True)
        self.repo.delete(sid)
        self.db.commit()

    def messages(self, principal, sid, limit, cursor):
        self.authorize(principal)
        self.owned(principal, sid, lock=True)
        before = decode_cursor(cursor, "messages", principal.id, str(sid))
        rows = self.repo.messages(sid, limit, before)
        items = rows[:limit]
        next_cursor = None
        if len(rows) > limit:
            next_cursor = encode_cursor(
                {
                    "kind": "messages",
                    "owner": str(principal.id),
                    "session": str(sid),
                    "sequence": items[-1]["sequence_number"],
                }
            )
        return MessageListResponse(
            items=[MessageResponse(**r) for r in reversed(items)],
            next_cursor=next_cursor,
        )
