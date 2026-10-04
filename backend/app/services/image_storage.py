"""Private file storage for user-uploaded images (IMAGE_STORAGE_DIR, never served directly).

Images are re-encoded before saving: EXIF orientation is applied and all
metadata (GPS location, camera serials) is dropped.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from app.core.identifiers import uuid7

FORMATS = {
    "JPEG": ("image/jpeg", "jpg", {"quality": 92}),
    "PNG": ("image/png", "png", {"optimize": True}),
    "WEBP": ("image/webp", "webp", {"quality": 90}),
}


@dataclass(frozen=True)
class StoredImage:
    storage_key: str
    mime_type: str
    size_bytes: int


class ImageStorage:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def save(self, img: Image.Image, fmt: str) -> StoredImage:
        mime, ext, options = FORMATS[fmt]
        clean = ImageOps.exif_transpose(img)
        if fmt == "JPEG" and clean.mode not in ("RGB", "L"):
            clean = clean.convert("RGB")
        buf = io.BytesIO()
        clean.save(buf, fmt, **options)  # no exif= → metadata is not written
        data = buf.getvalue()

        key = f"images/{uuid7().hex}.{ext}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return StoredImage(key, mime, len(data))

    def open(self, storage_key: str) -> Image.Image:
        img = Image.open(self._path(storage_key))
        img.load()
        return img

    def delete(self, storage_key: str) -> None:
        self._path(storage_key).unlink(missing_ok=True)

    def _path(self, storage_key: str) -> Path:
        path = (self.root / storage_key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"storage key escapes storage root: {storage_key!r}")
        return path
