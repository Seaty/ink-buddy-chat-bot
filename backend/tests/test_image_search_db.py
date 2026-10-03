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
    def __init__(self):
        self.analyze_calls = 0

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
    assert [(m.product_id, m.match_type) for m in res.matches] == [
        (ids[a], "exact"),
        (ids[b], "similar"),
    ]
    assert (
        res.matches[0].currency == "THB" and res.matches[0].availability is None
    )  # never invented


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
    service, vision = service_for(tmp_path, [(a, 0.30)])
    up = service.upload_image(db, user, jpeg())

    res = service.search_by_image(db, user, up.id, limit=5)
    assert (
        res.path == "full" and vision.analyze_calls == 1 and res.match_level == "none"
    )
    assert res.description == "ปากกาสีน้ำเงิน"
    saved = db.execute(
        text(
            "SELECT analysis->>'brand_text', ocr_text FROM image_uploads WHERE id = :id"
        ),
        {"id": up.id},
    ).one()
    assert tuple(saved) == ("Pentel", "Pentel BL667")
