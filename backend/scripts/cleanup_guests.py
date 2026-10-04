"""Idempotent cleanup; dry-run by default, --apply deletes expired unclaimed Guest data."""

import argparse
from datetime import timedelta

from app.core.config import get_settings
from app.core.security import utcnow
from app.db.database import get_sessionmaker
from app.services.image_storage import ImageStorage
from sqlalchemy import text


def cleanup(db, storage, retention_seconds, apply=False):
    cutoff = utcnow() - timedelta(seconds=retention_seconds)
    ids = (
        db.execute(
            text(
                "SELECT id FROM guest_sessions WHERE claimed_at IS NULL AND expires_at<=:cutoff ORDER BY id"
            ),
            {"cutoff": cutoff},
        )
        .scalars()
        .all()
    )
    count = 0
    for gid in ids:
        row = db.execute(
            text(
                "SELECT id FROM guest_sessions WHERE id=:id AND claimed_at IS NULL AND expires_at<=:cutoff FOR UPDATE"
            ),
            {"id": gid, "cutoff": cutoff},
        ).one_or_none()
        if not row:
            db.rollback()
            continue
        keys = (
            db.execute(
                text(
                    "SELECT storage_key FROM image_uploads WHERE guest_session_id=:id"
                ),
                {"id": gid},
            )
            .scalars()
            .all()
        )
        # Validate every path before deleting anything. Failed file deletion rolls back DB rows;
        # missing files are safe on retry because the session is already expired.
        for key in keys:
            storage._path(key)
        if apply:
            for key in keys:
                storage.delete(key)
            db.execute(
                text("DELETE FROM chat_sessions WHERE guest_session_id=:id"),
                {"id": gid},
            )
            db.execute(
                text("DELETE FROM image_uploads WHERE guest_session_id=:id"),
                {"id": gid},
            )
            db.execute(text("DELETE FROM guest_sessions WHERE id=:id"), {"id": gid})
            db.commit()
        else:
            db.rollback()
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    with get_sessionmaker()() as db:
        count = cleanup(
            db,
            ImageStorage(settings.image_storage_dir),
            settings.guest_retention_seconds,
            args.apply,
        )
    print(
        f"{count} Guest sessions "
        + ("deleted" if args.apply else "eligible; dry-run only")
    )


if __name__ == "__main__":
    main()
