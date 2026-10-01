"""Data access for image_uploads (table defined in database/ddl/001_init.sql).

Plain SQL on purpose: the schema is owned by the DDL, so no ORM model here
that create_all could try to create or drift from.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ImageUpload:
    id: UUID
    user_id: UUID
    storage_key: str
    mime_type: str
    size_bytes: int
    status: str
    analysis: dict | None = None  # cached vision-model reading (ImageAnalysis JSON)
    ocr_text: str | None = None  # cached OCR; "" = read, no text found; None = not read yet


class ImageUploadRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, user_id: UUID, storage_key: str, mime_type: str, size_bytes: int) -> ImageUpload:
        row = self.session.execute(
            text(
                "INSERT INTO image_uploads (user_id, storage_key, mime_type, size_bytes, status) "
                "VALUES (:user_id, :key, :mime, :size, 'ready') "
                "RETURNING id, user_id, storage_key, mime_type, size_bytes, status, analysis, ocr_text"
            ),
            {"user_id": user_id, "key": storage_key, "mime": mime_type, "size": size_bytes},
        ).one()
        return ImageUpload(*row)

    def get_owned(self, image_id: UUID, user_id: UUID) -> ImageUpload | None:
        """None when missing, soft-deleted, or owned by someone else (callers answer 404 either way)."""
        row = self.session.execute(
            text(
                "SELECT id, user_id, storage_key, mime_type, size_bytes, status, analysis, ocr_text FROM image_uploads "
                "WHERE id = :id AND user_id = :user_id AND deleted_at IS NULL"
            ),
            {"id": image_id, "user_id": user_id},
        ).one_or_none()
        return ImageUpload(*row) if row else None

    def save_analysis(self, image_id: UUID, analysis: dict) -> None:
        self.session.execute(
            text("UPDATE image_uploads SET analysis = CAST(:analysis AS jsonb) WHERE id = :id"),
            {"id": image_id, "analysis": json.dumps(analysis, ensure_ascii=False)},
        )

    def save_ocr(self, image_id: UUID, ocr_text: str) -> None:
        """Store real OCR output only ("" when the photo has no text)."""
        self.session.execute(text("UPDATE image_uploads SET ocr_text = :ocr WHERE id = :id"),
                             {"id": image_id, "ocr": ocr_text})
