import io

import pytest
from PIL import Image

from app.services.image_storage import ImageStorage


def photo_with_exif() -> Image.Image:
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotate 90° clockwise
    exif[0x010F] = "SecretCam"  # camera make
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), "blue").save(buf, "JPEG", exif=exif)
    return Image.open(io.BytesIO(buf.getvalue()))


def test_save_strips_metadata_and_applies_orientation(tmp_path):
    storage = ImageStorage(tmp_path)
    stored = storage.save(photo_with_exif(), "JPEG")
    assert stored.mime_type == "image/jpeg" and stored.storage_key.startswith("images/")
    assert (tmp_path / stored.storage_key).stat().st_size == stored.size_bytes
    img = storage.open(stored.storage_key)
    assert img.size == (20, 40)  # rotated upright
    assert not img.getexif()


def test_png_with_alpha_and_delete(tmp_path):
    storage = ImageStorage(tmp_path)
    stored = storage.save(Image.new("RGBA", (8, 8), (0, 0, 0, 0)), "PNG")
    assert stored.mime_type == "image/png" and storage.open(stored.storage_key).mode == "RGBA"
    storage.delete(stored.storage_key)
    assert not (tmp_path / stored.storage_key).exists()


@pytest.mark.parametrize("key", ["../outside.jpg", "images/../../outside.jpg"])
def test_storage_key_cannot_escape_root(tmp_path, key):
    with pytest.raises(ValueError):
        ImageStorage(tmp_path / "root").open(key)
