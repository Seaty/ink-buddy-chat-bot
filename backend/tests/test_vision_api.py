"""/api/v1 image endpoints + error format. No Ollama, DB or embedding model: fakes throughout."""

import io
import uuid
from pathlib import Path

import numpy as np
import pytest
from app.ai.prompts.vision_prompt import ImageAnalysis
from app.ai.rag.retriever import ImageRetriever, RetrievalQuery
from app.api.deps import authorize
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.rate_limit import limiter
from app.core.security import Principal
from app.db.database import get_db
from app.main import app
from app.schemas.vision import ImageUploadResponse, ProductSearchByImageResponse
from app.services.vision_service import VisionService, get_vision_service
from fastapi.testclient import TestClient
from PIL import Image

CATALOG = Path(__file__).resolve().parents[1] / "datasets" / "catalog"
USER = uuid.UUID("00000000-0000-0000-0000-000000000001")
IMAGE = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


class FakeService:
    def __init__(self, error: ApiError | None = None):
        self.error, self.calls = error, []

    def upload_image(self, db, user_id, data):
        user_id = user_id.id if isinstance(user_id, Principal) else user_id
        self.calls.append(("upload", user_id, len(data)))
        if self.error:
            raise self.error
        return ImageUploadResponse(id=IMAGE, status="ready")

    def search_by_image(self, db, user_id, image_id, limit):
        user_id = user_id.id if isinstance(user_id, Principal) else user_id
        self.calls.append(("search", user_id, image_id, limit))
        if self.error:
            raise self.error
        return ProductSearchByImageResponse(
            image_id=image_id,
            description=None,
            match_level="none",
            matches=[],
            path="fast",
        )


@pytest.fixture
def client():
    def _make(service=None, auth=True, **settings):
        limiter.reset()
        s = Settings(_env_file=None, image_max_bytes=200_000, **settings)
        app.dependency_overrides[get_vision_service] = lambda: service or FakeService()
        app.dependency_overrides[get_settings] = lambda: s
        app.dependency_overrides[get_db] = lambda: None
        if auth:
            app.dependency_overrides[authorize] = lambda: Principal(
                "user", USER, "user"
            )
        return TestClient(app, raise_server_exceptions=False)

    yield _make
    app.dependency_overrides.clear()


def jpeg(size=(120, 120)):
    buf = io.BytesIO()
    Image.new("RGB", size, "red").save(buf, "JPEG")
    return buf.getvalue()


def assert_error(r, status, code):
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and isinstance(
        body["error"]["details"], dict
    )
    return body["error"]


# --- /images -------------------------------------------------------------------
def test_upload_returns_201_and_id(client):
    service = FakeService()
    r = client(service).post(
        "/api/v1/images", files={"file": ("a.jpg", jpeg(), "image/jpeg")}
    )
    assert r.status_code == 201 and r.json() == {"id": str(IMAGE), "status": "ready"}
    assert service.calls[0][:2] == ("upload", USER)


def test_upload_without_auth_is_401(client):
    assert_error(
        client(auth=False).post(
            "/api/v1/images", files={"file": ("a.jpg", jpeg(), "image/jpeg")}
        ),
        401,
        "UNAUTHORIZED",
    )


def test_upload_too_large_is_413_before_service(client):
    service = FakeService()
    r = client(service).post(
        "/api/v1/images", files={"file": ("a.jpg", b"x" * 200_001, "image/jpeg")}
    )
    assert_error(r, 413, "IMAGE_TOO_LARGE")
    assert service.calls == []


def test_upload_service_error_keeps_code(client):
    service = FakeService(
        ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "file is not a readable image")
    )
    assert_error(
        client(service).post(
            "/api/v1/images", files={"file": ("a.jpg", b"nope", "image/jpeg")}
        ),
        415,
        "UNSUPPORTED_MEDIA_TYPE",
    )


def test_upload_missing_file_is_validation_error(client):
    err = assert_error(client().post("/api/v1/images"), 422, "VALIDATION_ERROR")
    assert err["details"]["errors"][0]["loc"][-1] == "file"


# --- /product-search/by-image ---------------------------------------------------
def test_search_passes_image_and_limit(client):
    service = FakeService()
    r = client(service).post(
        "/api/v1/product-search/by-image", json={"image_id": str(IMAGE), "limit": 3}
    )
    assert r.status_code == 200 and r.json()["image_id"] == str(IMAGE)
    assert service.calls == [("search", USER, IMAGE, 3)]


@pytest.mark.parametrize(
    "body",
    [
        {"image_id": "not-a-uuid"},
        {"image_id": str(IMAGE), "limit": 0},
        {"image_id": str(IMAGE), "limit": 11},
        {},
    ],
)
def test_search_validation(client, body):
    assert_error(
        client().post("/api/v1/product-search/by-image", json=body),
        422,
        "VALIDATION_ERROR",
    )


def test_search_not_found_and_unavailable(client):
    for status, code in ((404, "IMAGE_NOT_FOUND"), (503, "VISION_UNAVAILABLE")):
        service = FakeService(ApiError(status, code, "x"))
        assert_error(
            client(service).post(
                "/api/v1/product-search/by-image", json={"image_id": str(IMAGE)}
            ),
            status,
            code,
        )


# --- misc -------------------------------------------------------------------------
def test_admin_index_hidden_by_default(client):
    assert_error(client().post("/api/v1/admin/image-index"), 404, "NOT_FOUND")


def test_unknown_route_uses_error_format(client):
    assert_error(client().get("/api/v1/nope"), 404, "NOT_FOUND")


def test_unhandled_error_is_500_without_details(client):
    class Boom(FakeService):
        def upload_image(self, *a):
            raise RuntimeError("secret internals")

    err = assert_error(
        client(Boom()).post(
            "/api/v1/images", files={"file": ("a.jpg", jpeg(), "image/jpeg")}
        ),
        500,
        "INTERNAL_ERROR",
    )
    assert "secret" not in err["message"]


def test_health(client):
    assert client().get("/api/v1/health").json() == {"status": "ok"}


@pytest.mark.parametrize(
    "data, status, code",
    [
        (b"", 422, "EMPTY_FILE"),
        (b"nope", 415, "UNSUPPORTED_MEDIA_TYPE"),
        (None, 422, "IMAGE_TOO_SMALL"),
    ],
)
def test_service_maps_invalid_images(data, status, code):
    service = VisionService(
        Settings(_env_file=None), pipeline=object(), storage=object()
    )
    data = jpeg((10, 10)) if data is None else data
    with pytest.raises(ApiError) as e:
        service.upload_image(None, USER, data)  # fails before touching storage or DB
    assert (e.value.status, e.value.code) == (status, code)


# --- ImageRetriever with fake embedder + fake index ---------------------------
class FakeEmbedder:
    def embed_images(self, images, instruction=None):
        return np.array([[1.0, 0.0]])

    def embed_texts(self, texts, instruction=None):
        return np.array([[0.0, 1.0]])


class FakeIndex:
    def __init__(self, image_hits, caption_hits):
        self.hits = {"image": image_hits, "caption": caption_hits}

    def best_by_sku(self, vector, chunk_type, limit):
        return self.hits[chunk_type]


def _query(text="desc", **analysis):
    base = {
        "is_stationery": True,
        "intent": "find_similar",
        "category_guess": "ruler",
        "description": "x",
    }
    return RetrievalQuery(
        Image.new("RGB", (8, 8)),
        text,
        ImageAnalysis.model_validate({**base, **analysis}),
    )


def test_image_retriever_hybrid_score_and_boosts():
    meta = lambda cat, brand: {"category": cat, "brand": brand}
    index = FakeIndex(
        {"a": (0.9, meta("ruler", "Maped")), "b": (0.7, meta("glue", "UHU"))},
        {"a": (0.5, meta("ruler", "Maped")), "c": (0.8, meta("ruler", "Deli"))},
    )
    out = ImageRetriever(FakeEmbedder(), index).search(
        _query(brand_text="MAPED"), top_k=3
    )
    scores = {d["category"] + d["brand"]: d["score"] for d in out}
    assert scores["rulerMaped"] == pytest.approx(0.6 * 0.9 + 0.4 * 0.5 + 0.05 + 0.10)
    assert scores["glueUHU"] == pytest.approx(0.6 * 0.7)
    assert scores["rulerDeli"] == pytest.approx(0.4 * 0.8 + 0.05)
    assert out[0]["brand"] == "Maped"


def test_image_retriever_without_text_uses_image_only():
    index = FakeIndex({"a": (0.7, {"category": "glue", "brand": "X"})}, {})
    out = ImageRetriever(FakeEmbedder(), index).search(_query(text=" "), top_k=1)
    assert out[0]["score"] == pytest.approx(0.7)
