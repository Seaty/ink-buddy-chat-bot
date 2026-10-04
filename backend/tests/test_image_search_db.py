"""VisionService upload + by-image search against the real team schema (database/ddl/001_init.sql).

Runs only with TEST_DATABASE_URL pointing at a database with the init DDL and
the catalog seed. Everything happens inside one outer transaction that is
rolled back, so no rows are left behind (service commits become savepoints).
"""

import io
import os
import uuid
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.ai.prompts.vision_prompt import ImageAnalysis
from app.ai.vision.image_analyzer import ImageAnalyzer
from app.ai.vision.vision_pipeline import PipelineSettings, VisionPipeline
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.identifiers import uuid7
from app.services.image_storage import ImageStorage
from app.services.vision_service import VisionService

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")
CATALOG = Path(__file__).resolve().parents[1] / "datasets" / "catalog"


@pytest.fixture
def db():
    engine = create_engine(URL)
    conn = engine.connect()
    outer = conn.begin()
    if not conn.execute(text("SELECT to_regclass('public.image_uploads')")).scalar():
        pytest.skip("team schema (001_init.sql) not present")
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    outer.rollback()
    conn.close()
    engine.dispose()


def make_user(db) -> uuid.UUID:
    return db.execute(
        text(
            "INSERT INTO users (role_id, email, password_hash) "
            "SELECT id, :e, '!' FROM roles WHERE name = 'user' RETURNING id"
        ),
        {"e": f"t-{uuid7().hex}@test"},
    ).scalar_one()


def seeded_skus(db, n=2) -> list[str]:
    skus = list(
        db.execute(
            text(
                "SELECT sku FROM products WHERE sku IS NOT NULL ORDER BY sku LIMIT :n"
            ),
            {"n": n},
        ).scalars()
    )
    if len(skus) < n:
        pytest.skip("catalog seed not loaded")
    return skus


class FakeVision:
    def __init__(self, ocr_segments=("Pentel", "BL667")):
        self.analyze_calls = 0
        self.ocr_calls = 0
        self.ocr_segments = list(ocr_segments)

    def ocr(self, image):
        self.ocr_calls += 1
        return self.ocr_segments

    def analyze(self, image, message=None):
        self.analyze_calls += 1
        return ImageAnalysis(
            is_stationery=True,
            intent="find_similar",
            category_guess="other",
            brand_text="Pentel",
            model_text="BL667",
            description="ปากกาสีน้ำเงิน",
        )

    def answer(self, *a, **k):
        raise AssertionError("by-image must not generate an answer")


class Retriever:
    def __init__(self, hits):
        self.hits = hits  # [(sku, score)]

    def search(self, query, top_k):
        return [
            {
                "sku": s,
                "score": sc,
                "category": "other",
                "name": s,
                "price_thb": 1.0,
                "unit": None,
                "pack_qty": None,
                "unit_price": None,
                "price_date": "2026-09-27",
                "stock_qty": None,
                "brand": "x",
                "category_th": "x",
                "source_url": "x",
                "image_url": "x",
                "image_path": "x",
            }
            for s, sc in self.hits
        ][:top_k]


def service_for(tmp_path, hits):
    vision = FakeVision()
    pipeline = VisionPipeline(
        ImageAnalyzer(vision), Retriever(hits), PipelineSettings(catalog_dir=CATALOG)
    )
    return VisionService(
        Settings(_env_file=None), pipeline, ImageStorage(tmp_path)
    ), vision


def jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (120, 120), "red").save(buf, "JPEG")
    return buf.getvalue()


def test_upload_then_fast_search_maps_to_product_ids(db, tmp_path):
    a, b = seeded_skus(db)
    user = make_user(db)
    service, vision = service_for(
        tmp_path, [(a, 0.93), (b, 0.70), ("not_in_catalog", 0.65)]
    )

    up = service.upload_image(db, user, jpeg())
    row = db.execute(
        text("SELECT user_id, mime_type, status FROM image_uploads WHERE id = :id"),
        {"id": up.id},
    ).one()
    assert (row.user_id, row.mime_type, row.status) == (user, "image/jpeg", "ready")

    res = service.search_by_image(db, user, up.id, limit=5)
    ids = dict(
        db.execute(
            text("SELECT sku, id FROM products WHERE sku IN (:a, :b)"), {"a": a, "b": b}
        ).all()
    )
    assert res.path == "fast" and vision.analyze_calls == 0 and res.description is None
    # fast path cannot verify the model from the photo → never "exact"
    assert res.match_level == "similar"
    assert [(m.product_id, m.match_type) for m in res.matches] == [(ids[a], "similar"), (ids[b], "similar")]
    assert res.matches[0].currency == "THB" and res.matches[0].availability is None  # never invented


def test_image_of_another_user_is_not_found(db, tmp_path):
    owner, other = make_user(db), make_user(db)
    service, _ = service_for(tmp_path, [])
    up = service.upload_image(db, owner, jpeg())
    with pytest.raises(ApiError) as e:
        service.search_by_image(db, other, up.id, limit=5)
    assert (e.value.status, e.value.code) == (404, "IMAGE_NOT_FOUND")


def test_no_match_uses_vlm_and_saves_analysis(db, tmp_path):
    (a,) = seeded_skus(db, 1)
    user = make_user(db)
    service, vision = service_for(tmp_path, [(a, 0.50)])
    up = service.upload_image(db, user, jpeg())

    res = service.search_by_image(db, user, up.id, limit=5)
    assert (
        res.path == "full" and vision.analyze_calls == 1 and res.match_level == "none"
    )
    assert res.description == "ปากกาสีน้ำเงิน"
    # nothing matched: no "similar" matches, but the nearest product is offered as a suggestion
    product_id = db.execute(text("SELECT id FROM products WHERE sku = :s"), {"s": a}).scalar_one()
    assert res.matches == []
    assert [(m.product_id, m.match_type) for m in res.suggestions] == [(product_id, "suggestion")]
    assert res.message.startswith("ไม่พบสินค้าที่ตรงกับในรูปค่ะ หมายถึงสินค้าเหล่านี้หรือเปล่าคะ?")
    saved = db.execute(text("SELECT analysis->>'brand_text', ocr_text FROM image_uploads WHERE id = :id"),
                       {"id": up.id}).one()
    assert tuple(saved) == ("Pentel", None)  # brand/model readings are not stored as OCR

    # the stored analysis is reused by /analysis without another model call
    analysis = service.analyze_image(db, user, up.id)
    assert analysis.cached and analysis.attributes.brand_text == "Pentel" and vision.analyze_calls == 1


def test_analysis_runs_once_then_cached(db, tmp_path):
    user = make_user(db)
    service, vision = service_for(tmp_path, [])
    up = service.upload_image(db, user, jpeg())
    first = service.analyze_image(db, user, up.id)
    second = service.analyze_image(db, user, up.id)
    assert (first.cached, second.cached, vision.analyze_calls) == (False, True, 1)
    assert second.description == "ปากกาสีน้ำเงิน" and second.attributes.model_text == "BL667"


def test_ocr_runs_once_then_cached(db, tmp_path):
    user = make_user(db)
    service, vision = service_for(tmp_path, [])
    up = service.upload_image(db, user, jpeg())
    first = service.ocr_image(db, user, up.id)
    second = service.ocr_image(db, user, up.id)
    assert (first.cached, second.cached, vision.ocr_calls) == (False, True, 1)
    assert second.text == "Pentel\nBL667" and [s.text for s in second.segments] == ["Pentel", "BL667"]


def test_ocr_with_no_text_is_cached_as_empty(db, tmp_path):
    user = make_user(db)
    vision = FakeVision(ocr_segments=())
    pipeline = VisionPipeline(ImageAnalyzer(vision), Retriever([]), PipelineSettings(catalog_dir=CATALOG))
    service = VisionService(Settings(_env_file=None), pipeline, ImageStorage(tmp_path))
    up = service.upload_image(db, user, jpeg())
    assert service.ocr_image(db, user, up.id).text == ""
    again = service.ocr_image(db, user, up.id)
    assert again.cached and again.segments == [] and vision.ocr_calls == 1


def test_analysis_and_ocr_check_ownership(db, tmp_path):
    owner, other = make_user(db), make_user(db)
    service, vision = service_for(tmp_path, [])
    up = service.upload_image(db, owner, jpeg())
    for call in (service.analyze_image, service.ocr_image):
        with pytest.raises(ApiError) as e:
            call(db, other, up.id)
        assert e.value.code == "IMAGE_NOT_FOUND"
    assert vision.analyze_calls == vision.ocr_calls == 0


def test_full_path_exact_when_model_read_from_photo(db, tmp_path):
    """FakeVision reads "Pentel BL667"; only the seeded Energel BL667 name contains it."""
    energel = db.execute(text("SELECT sku, name FROM products WHERE name ILIKE '%BL667%'")).first()
    other = db.execute(text("SELECT sku, name FROM products WHERE name NOT ILIKE '%BL667%' ORDER BY sku")).first()
    if energel is None or other is None:
        pytest.skip("catalog seed not loaded")
    names = {energel.sku: energel.name, other.sku: other.name}
    user = make_user(db)

    class Named(Retriever):
        def search(self, query, top_k):
            return [{**p, "name": names[p["sku"]]} for p in super().search(query, top_k)]

    pipeline = VisionPipeline(ImageAnalyzer(FakeVision()), Named([(other.sku, 0.80), (energel.sku, 0.62)]),
                              PipelineSettings(catalog_dir=CATALOG, fast_path=False))
    service = VisionService(Settings(_env_file=None), pipeline, ImageStorage(tmp_path))
    up = service.upload_image(db, user, jpeg())
    res = service.search_by_image(db, user, up.id, limit=5)
    assert res.match_level == "exact"
    assert (res.matches[0].sku, res.matches[0].match_type) == (energel.sku, "exact")
    assert res.matches[1].match_type == "similar"


# --- Guest principals on /analysis and /ocr ----------------------------------------
from app.core.security import Principal  # noqa: E402


def make_guest(db, expired=False) -> Principal:
    """A guest_sessions row; expired ones were created two hours ago and expired one hour ago."""
    when = ("now() - interval '2 hours'", "now() - interval '1 hour'") if expired else ("now()", "now() + interval '1 hour'")
    gid = db.execute(text(
        f"INSERT INTO guest_sessions (token_hash, created_at, expires_at) VALUES (:h, {when[0]}, {when[1]}) RETURNING id"
    ), {"h": f"test-{uuid7().hex}"}).scalar_one()
    return Principal("guest", gid)


def test_guest_owns_analysis_and_ocr_of_own_upload(db, tmp_path):
    guest = make_guest(db)
    service, vision = service_for(tmp_path, [])
    up = service.upload_image(db, guest, jpeg())
    assert service.analyze_image(db, guest, up.id).attributes.model_text == "BL667"
    assert service.ocr_image(db, guest, up.id).text == "Pentel\nBL667"
    used = db.execute(text("SELECT image_uploads_used FROM guest_sessions WHERE id = :id"), {"id": guest.id}).scalar_one()
    assert used == 1  # analysis/OCR do not consume upload quota


def test_other_guest_and_user_get_404_for_guest_image(db, tmp_path):
    owner, other_guest, user = make_guest(db), make_guest(db), make_user(db)
    service, vision = service_for(tmp_path, [])
    up = service.upload_image(db, owner, jpeg())
    for principal in (other_guest, user):
        for call in (service.analyze_image, service.ocr_image):
            with pytest.raises(ApiError) as e:
                call(db, principal, up.id)
            assert (e.value.status, e.value.code) == (404, "IMAGE_NOT_FOUND")
    assert vision.analyze_calls == vision.ocr_calls == 0


def test_expired_guest_is_unauthorized_for_analysis_and_ocr(db, tmp_path):
    live = make_guest(db)
    service, vision = service_for(tmp_path, [])
    up = service.upload_image(db, live, jpeg())
    db.execute(text("UPDATE guest_sessions SET created_at = now() - interval '2 hours', "
                    "expires_at = now() - interval '1 hour' WHERE id = :id"), {"id": live.id})
    for call in (service.analyze_image, service.ocr_image):
        with pytest.raises(ApiError) as e:
            call(db, live, up.id)
        assert e.value.status == 401
    assert vision.analyze_calls == vision.ocr_calls == 0
