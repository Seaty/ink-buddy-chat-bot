"""Chat data access. The service owns transactions and lock ordering."""

from sqlalchemy import text


class SessionRepository:
    def __init__(self, db):
        self.db = db

    def owner(self, principal):
        return "user_id" if principal.kind == "user" else "guest_session_id"

    def create(self, principal, title):
        return (
            self.db.execute(
                text(
                    f"INSERT INTO chat_sessions ({self.owner(principal)},title) VALUES (:owner,:title) RETURNING *"
                ),
                {"owner": principal.id, "title": title},
            )
            .mappings()
            .one()
        )

    def get(self, principal, sid, lock=False):
        return (
            self.db.execute(
                text(
                    f"SELECT * FROM chat_sessions WHERE id=:id AND {self.owner(principal)}=:owner AND deleted_at IS NULL"
                    + (" FOR UPDATE" if lock else "")
                ),
                {"id": sid, "owner": principal.id},
            )
            .mappings()
            .one_or_none()
        )

    def list(self, principal, limit, boundary):
        params = {"owner": principal.id, "limit": limit + 1}
        clause = ""
        if boundary:
            clause = " AND (updated_at,id)<(:time,:id)"
            params.update(time=boundary[0], id=boundary[1])
        return (
            self.db.execute(
                text(
                    f"SELECT * FROM chat_sessions WHERE {self.owner(principal)}=:owner AND deleted_at IS NULL{clause} ORDER BY updated_at DESC,id DESC LIMIT :limit"
                ),
                params,
            )
            .mappings()
            .all()
        )

    def rename(self, sid, title):
        return (
            self.db.execute(
                text(
                    "UPDATE chat_sessions SET title=:title,updated_at=clock_timestamp() WHERE id=:id RETURNING *"
                ),
                {"id": sid, "title": title},
            )
            .mappings()
            .one()
        )

    def delete(self, sid):
        self.db.execute(
            text(
                "UPDATE chat_sessions SET deleted_at=clock_timestamp(),updated_at=clock_timestamp() WHERE id=:id"
            ),
            {"id": sid},
        )

    def messages(self, sid, limit, before):
        return (
            self.db.execute(
                text(
                    "SELECT * FROM chat_messages WHERE session_id=:sid AND sequence_number<:before ORDER BY sequence_number DESC LIMIT :limit"
                ),
                {"sid": sid, "before": before or 2147483648, "limit": limit + 1},
            )
            .mappings()
            .all()
        )
