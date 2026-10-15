"""Real PostgreSQL auth, image ownership and transaction/concurrency tests.
Run with python -m scripts.test_auth_postgres; never use the application DB.
"""

import io
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import bcrypt
import pytest
from fastapi.testclient import TestClient
from jose import jwt
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.ai.prompts.vision_prompt import Intent, MatchLevel
from app.ai.vision.vision_pipeline import VisionResult
from app.api.deps import GUEST_COOKIE, REFRESH_COOKIE
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.rate_limit import limiter
from app.core.security import Principal, hash_password, utcnow
from app.db.database import get_db
from app.main import create_app
from app.services.auth.service import AuthService
from app.services.image_storage import ImageStorage
from app.services.vision_service import VisionService, get_vision_service
from fastapi.testclient import TestClient
from jose import jwt
from PIL import Image
from scripts.cleanup_guests import cleanup
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

URL = os.environ.get("INK_BUDDY_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not URL, reason="Run scripts.test_auth_postgres with isolated Podman PostgreSQL"
)
ORIGIN = {"Origin": "http://localhost:3000"}
PASSWORD = "Correct password 123!"


@pytest.fixture
def setup(tmp_path):
    assert "ink_buddy_test_" in URL, (
        "Refuse integration tests against application database"
    )
    engine = create_engine(URL, pool_size=10, max_overflow=10)
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE users,guest_sessions,products RESTART IDENTITY CASCADE")
        )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        database_url=URL,
        auth_jwt_secret="test-only-signing-key-never-use-in-production-12345",
        image_storage_dir=tmp_path,
    )
    ids = {}
    with sessions() as db:
        for role, email in [
            ("user", "user@example.com"),
            ("admin", "admin@example.com"),
        ]:
            ids[role] = db.execute(
                text(
                    "INSERT INTO users(role_id,email,password_hash) SELECT id,:email,:hash FROM roles WHERE name=:role RETURNING id"
                ),
                {"email": email, "hash": hash_password(PASSWORD), "role": role},
            ).scalar_one()
        db.commit()
    app = create_app(settings)

    def database():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = database

    class EmptyPipeline:
        def run(self, *args, **kwargs):
            # a real VisionResult, so new result fields (e.g. suggestions) keep the fake valid
            return VisionResult(
                answer="", intent=Intent.FIND_SIMILAR, match_level=MatchLevel.NONE, path="fast"
            )

    vision = VisionService(settings, pipeline=EmptyPipeline())
    app.dependency_overrides[get_vision_service] = lambda: vision
    limiter.reset()
    limiter.enabled = False
    yield SimpleNamespace(
        app=app,
        settings=settings,
        sessions=sessions,
        ids=ids,
        vision=vision,
        storage=ImageStorage(tmp_path),
    )
    limiter.enabled = True
    limiter.reset()
    engine.dispose()


def image_bytes():
    data = io.BytesIO()
    Image.new("RGB", (64, 64)).save(data, "PNG")
    return data.getvalue()


def login(client, role="user"):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": role + "@example.com", "password": PASSWORD},
        headers=ORIGIN,
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def guest(client):
    response = client.post("/api/v1/auth/guest-sessions", headers=ORIGIN)
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, headers=None):
    return client.post(
        "/api/v1/images",
        files={"file": ("image.png", image_bytes(), "image/png")},
        headers=headers or ORIGIN,
    )


def test_login_refresh_logout_immediate(setup):
    with TestClient(setup.app) as client:
        token = login(client)
        raw = client.cookies[REFRESH_COOKIE]
        headers = {"Authorization": "Bearer " + token}
        assert client.get("/api/v1/users/me", headers=headers).status_code == 200
        response = client.post("/api/v1/auth/refresh", headers=ORIGIN)
        assert response.status_code == 200, response.text
        assert raw != client.cookies[REFRESH_COOKIE]
        token = response.json()["access_token"]
        assert client.post("/api/v1/auth/logout", headers=ORIGIN).status_code == 204
        assert REFRESH_COOKIE not in client.cookies
        assert (
            client.get(
                "/api/v1/users/me", headers={"Authorization": "Bearer " + token}
            ).status_code
            == 401
        )
        assert client.get("/api/v1/users/me", headers=headers).status_code == 401


def test_login_failure_inactive_and_bcrypt_upgrade(setup):
    with TestClient(setup.app) as client:
        errors = []
        for email, password in [
            ("missing@example.com", PASSWORD),
            ("user@example.com", "wrong"),
        ]:
            r = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password},
                headers=ORIGIN,
            )
            assert r.status_code == 401
            errors.append(r.json())
        assert errors[0] == errors[1]
        with setup.sessions() as db:
            db.execute(
                text("UPDATE users SET password_hash=:hash WHERE id=:id"),
                {
                    "hash": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
                    "id": setup.ids["user"],
                },
            )
            db.commit()
        login(client)
        with setup.sessions() as db:
            assert (
                db.execute(
                    text("SELECT password_hash FROM users WHERE id=:id"),
                    {"id": setup.ids["user"]},
                )
                .scalar()
                .startswith("$argon2id$")
            )
            db.execute(
                text("UPDATE users SET is_active=false WHERE id=:id"),
                {"id": setup.ids["user"]},
            )
            db.commit()
        r = client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.com", "password": PASSWORD},
            headers=ORIGIN,
        )
        assert r.status_code == 401 and r.json() == errors[0]


def test_jwt_tamper_expiry_and_account_disabled(setup):
    with TestClient(setup.app) as client:
        token = login(client)
        claims = jwt.get_unverified_claims(token)
        variants = [
            token[:-8] + "invalid!",
            jwt.encode(
                {**claims, "exp": int((utcnow() - timedelta(seconds=5)).timestamp())},
                setup.settings.auth_jwt_secret,
                algorithm="HS256",
            ),
            jwt.encode(
                {**claims, "aud": "other"},
                setup.settings.auth_jwt_secret,
                algorithm="HS256",
            ),
        ]
        for value in variants:
            assert (
                client.get(
                    "/api/v1/users/me", headers={"Authorization": "Bearer " + value}
                ).status_code
                == 401
            )
        with setup.sessions() as db:
            db.execute(
                text("UPDATE users SET is_active=false WHERE id=:id"),
                {"id": setup.ids["user"]},
            )
            db.commit()
        assert (
            client.get(
                "/api/v1/users/me", headers={"Authorization": "Bearer " + token}
            ).status_code
            == 401
        )


def test_refresh_reuse_revokes_family_and_absolute_expiry(setup):
    with TestClient(setup.app) as client:
        first = login(client)
        old = client.cookies[REFRESH_COOKIE]
        with setup.sessions() as db:
            expiry = db.execute(
                text("SELECT expires_at FROM auth_sessions")
            ).scalar_one()
        response = client.post("/api/v1/auth/refresh", headers=ORIGIN)
        assert response.status_code == 200
        fresh = response.json()["access_token"]
        with setup.sessions() as db:
            assert (
                db.execute(text("SELECT expires_at FROM auth_sessions")).scalar_one()
                == expiry
            )
        client.cookies.set(
            REFRESH_COOKIE, old, domain="testserver.local", path="/api/v1"
        )
        assert client.post("/api/v1/auth/refresh", headers=ORIGIN).status_code == 401
        for access in [first, fresh]:
            assert (
                client.get(
                    "/api/v1/users/me", headers={"Authorization": "Bearer " + access}
                ).status_code
                == 401
            )


def test_concurrent_refresh_has_one_rotation_then_reuse_revocation(setup):
    with setup.sessions() as db:
        _, raw, _ = AuthService(db, setup.settings).login("user@example.com", PASSWORD)

    def refresh():
        with setup.sessions() as db:
            try:
                return AuthService(db, setup.settings).refresh(raw)[0].access_token
            except ApiError as e:
                return e.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: refresh(), range(2)))
    assert sum(isinstance(x, str) for x in results) == 1 and results.count(401) == 1
    with setup.sessions() as db:
        assert db.execute(
            text("SELECT revoked_at IS NOT NULL FROM auth_sessions")
        ).scalar_one()


def test_guest_reuse_cookie_security_and_no_bearer_fallback(setup):
    with TestClient(setup.app) as client:
        first = guest(client)
        raw = client.cookies[GUEST_COOKIE]
        response = client.post("/api/v1/auth/guest-sessions", headers=ORIGIN)
        assert (
            response.status_code == 200
            and response.json() == first
            and client.cookies[GUEST_COOKIE] == raw
        )
        cookie = response.headers["set-cookie"].lower()
        assert (
            "httponly" in cookie
            and "samesite=lax" in cookie
            and "path=/api/v1" in cookie
        )
        assert client.get("/api/v1/products").status_code == 501
        assert (
            client.get(
                "/api/v1/products", headers={"Authorization": "Bearer invalid"}
            ).status_code
            == 401
        )
        assert client.get("/api/v1/users/me").status_code == 401
        assert (
            client.post("/api/v1/admin/image-index", headers=ORIGIN).status_code == 401
        )
        assert (
            upload(client, headers={"Origin": "https://evil.example"}).status_code
            == 403
        )
        assert client.post("/api/v1/auth/guest-sessions").status_code == 403
        assert (
            client.options(
                "/api/v1/images",
                headers={**ORIGIN, "Access-Control-Request-Method": "POST"},
            ).status_code
            == 200
        )


def test_guest_quota_validation_reuse_and_cross_owner(setup):
    with TestClient(setup.app) as a, TestClient(setup.app) as b:
        guest(a)
        guest(b)
        bad = a.post(
            "/api/v1/images",
            files={"file": ("x.png", b"not image", "image/png")},
            headers=ORIGIN,
        )
        assert bad.status_code == 415
        ids = []
        for _ in range(3):
            r = upload(a)
            assert r.status_code == 201, r.text
            ids.append(r.json()["id"])
        r = upload(a)
        assert (
            r.status_code == 403
            and r.json()["error"]["code"] == "GUEST_IMAGE_QUOTA_EXCEEDED"
        )
        assert (
            a.get("/api/v1/auth/guest-sessions/current").json()[
                "image_uploads_remaining"
            ]
            == 0
        )
        assert (
            a.post(
                "/api/v1/product-search/by-image",
                json={"image_id": ids[0]},
                headers=ORIGIN,
            ).status_code
            == 200
        )
        assert (
            b.post(
                "/api/v1/product-search/by-image",
                json={"image_id": ids[0]},
                headers=ORIGIN,
            ).status_code
            == 404
        )
        token = login(b)
        assert (
            b.post(
                "/api/v1/product-search/by-image",
                json={"image_id": ids[0]},
                headers={"Authorization": "Bearer " + token},
            ).status_code
            == 404
        )
        assert (
            a.get("/api/v1/auth/guest-sessions/current").json()["image_uploads_used"]
            == 3
        )


def test_concurrent_upload_never_exceeds_three(setup):
    with setup.sessions() as db:
        result, _, _ = AuthService(db, setup.settings).create_guest(None)
    owner = Principal("guest", result.id)

    def send():
        with setup.sessions() as db:
            try:
                setup.vision.upload_image(db, owner, image_bytes())
                return 201
            except ApiError as e:
                return e.status

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: send(), range(6)))
    assert results.count(201) == 3 and results.count(403) == 3
    with setup.sessions() as db:
        assert (
            db.execute(
                text("SELECT image_uploads_used FROM guest_sessions")
            ).scalar_one()
            == 3
        )
        assert db.execute(text("SELECT count(*) FROM image_uploads")).scalar_one() == 3
    assert len(list(setup.settings.image_storage_dir.rglob("*.png"))) == 3


def test_upload_database_failure_rolls_back_counter_and_file(setup, monkeypatch):
    from app.repositories.image_repository import ImageUploadRepository

    with setup.sessions() as db:
        result, _, _ = AuthService(db, setup.settings).create_guest(None)

    def fail(*args):
        raise RuntimeError("simulated insert failure")

    monkeypatch.setattr(ImageUploadRepository, "create", fail)
    with setup.sessions() as db:
        with pytest.raises(RuntimeError):
            setup.vision.upload_image(db, Principal("guest", result.id), image_bytes())
    with setup.sessions() as db:
        assert (
            db.execute(
                text("SELECT image_uploads_used FROM guest_sessions")
            ).scalar_one()
            == 0
        )
    assert list(setup.settings.image_storage_dir.rglob("*.png")) == []


def test_claim_moves_all_owners_revokes_guest_and_keeps_image_private(setup):
    with TestClient(setup.app) as client:
        g = guest(client)
        raw = client.cookies[GUEST_COOKIE]
        image = upload(client).json()["id"]
        with setup.sessions() as db:
            db.execute(
                text(
                    "INSERT INTO chat_sessions(guest_session_id,title) VALUES(:id,:title)"
                ),
                {"id": UUID(g["id"]), "title": "Guest chat"},
            )
            db.commit()
        token = login(client)
        h = {**ORIGIN, "Authorization": "Bearer " + token}
        r = client.post("/api/v1/auth/guest-sessions/current/claim", headers=h)
        assert r.status_code == 200, r.text
        assert (
            r.json()["chat_sessions_claimed"] == 1 and r.json()["images_claimed"] == 1
        )
        assert GUEST_COOKIE not in client.cookies
        client.cookies.set(GUEST_COOKIE, raw, domain="testserver.local", path="/api/v1")
        assert client.get("/api/v1/auth/guest-sessions/current").status_code == 401
        assert (
            client.post(
                "/api/v1/auth/guest-sessions/current/claim", headers=h
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/v1/product-search/by-image", json={"image_id": image}, headers=h
            ).status_code
            == 200
        )
        with setup.sessions() as db:
            assert (
                db.execute(text("SELECT user_id FROM chat_sessions")).scalar_one()
                == setup.ids["user"]
            )
            assert (
                db.execute(
                    text("SELECT guest_session_id FROM image_uploads")
                ).scalar_one()
                is None
            )


def test_claim_and_upload_serialize(setup):
    with setup.sessions() as db:
        result, raw, _ = AuthService(db, setup.settings).create_guest(None)

    def claim():
        with setup.sessions() as db:
            return AuthService(db, setup.settings).claim(
                Principal("user", setup.ids["user"]), raw
            )

    def send():
        with setup.sessions() as db:
            try:
                setup.vision.upload_image(
                    db, Principal("guest", result.id), image_bytes()
                )
                return 201
            except ApiError as e:
                return e.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(claim)
        two = pool.submit(send)
        one.result()
        assert two.result() in [201, 401]
    with setup.sessions() as db:
        assert (
            db.execute(
                text(
                    "SELECT count(*) FROM image_uploads WHERE guest_session_id IS NOT NULL"
                )
            ).scalar_one()
            == 0
        )
        assert (
            db.execute(
                text(
                    "SELECT count(*) FROM image_uploads WHERE user_id IS DISTINCT FROM :id"
                ),
                {"id": setup.ids["user"]},
            ).scalar_one()
            == 0
        )


def test_expired_guest_cleanup_dry_run_idempotent_and_claimed_data(setup):
    with setup.sessions() as db:
        result, raw, _ = AuthService(db, setup.settings).create_guest(None)
        setup.vision.upload_image(db, Principal("guest", result.id), image_bytes())
        db.execute(
            text(
                "UPDATE guest_sessions SET created_at=now()-interval '4 days',expires_at=now()-interval '2 days' WHERE id=:id"
            ),
            {"id": result.id},
        )
        db.commit()
        with pytest.raises(ApiError):
            AuthService(db, setup.settings).authenticate_guest(raw)
        assert cleanup(db, setup.storage, 86400, False) == 1
        assert db.execute(text("SELECT count(*) FROM guest_sessions")).scalar_one() == 1
        assert cleanup(db, setup.storage, 86400, True) == 1
        assert cleanup(db, setup.storage, 86400, True) == 0
        assert list(setup.settings.image_storage_dir.rglob("*.png")) == []
        claimed, claimed_raw, _ = AuthService(db, setup.settings).create_guest(None)
        setup.vision.upload_image(db, Principal("guest", claimed.id), image_bytes())
        AuthService(db, setup.settings).claim(
            Principal("user", setup.ids["user"]), claimed_raw
        )
        db.execute(
            text(
                "UPDATE guest_sessions SET created_at=now()-interval '4 days',expires_at=now()-interval '2 days'"
            )
        )
        db.commit()
        assert cleanup(db, setup.storage, 86400, True) == 0
        assert db.execute(text("SELECT count(*) FROM image_uploads")).scalar_one() == 1


def test_user_admin_and_rate_limit(setup):
    with TestClient(setup.app) as client:
        token = login(client)
        assert (
            client.post(
                "/api/v1/admin/image-index",
                headers={"Authorization": "Bearer " + token},
            ).status_code
            == 403
        )
        admin = login(client, "admin")
        assert (
            client.post(
                "/api/v1/admin/image-index",
                headers={"Authorization": "Bearer " + admin},
            ).status_code
            == 404
        )
        assert (
            client.get(
                "/api/v1/ready", headers={"Authorization": "Bearer " + admin}
            ).status_code
            == 501
        )
        limiter.enabled = True
        limiter.reset()
        for _ in range(5):
            assert client.post(
                "/api/v1/auth/guest-sessions", headers=ORIGIN
            ).status_code in (200, 201)
        r = client.post("/api/v1/auth/guest-sessions", headers=ORIGIN)
        assert (
            r.status_code == 429
            and r.json()["error"]["code"] == "RATE_LIMITED"
            and "retry-after" in r.headers
        )


def test_production_cookie_and_docs(setup):
    settings = setup.settings.model_copy(
        update={
            "app_environment": "production",
            "auth_frontend_url": "https://ink-buddy.example",
            "smtp_starttls": True,
        }
    )
    app = create_app(settings)
    app.dependency_overrides[get_db] = setup.app.dependency_overrides[get_db]
    with TestClient(app, base_url="https://testserver") as client:
        r = client.post("/api/v1/auth/guest-sessions", headers=ORIGIN)
        assert r.status_code == 201
        assert "secure" in r.headers["set-cookie"].lower()
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_migration_preserves_users_and_revokes_legacy_refresh(setup):
    # Start from previous DDL shape in an isolated schema, then run migration 003.
    import re

    ddl = Path("../database/ddl/001_init.sql").read_text(encoding="utf-8")
    ddl = re.sub(
        r"CREATE TABLE auth_sessions .*?(?=CREATE TABLE refresh_tokens)",
        "",
        ddl,
        flags=re.S,
    )
    ddl = re.sub(
        r"^.*(?:session_id uuid,|rotated_at timestamptz,|replaced_by_id uuid REFERENCES refresh_tokens|CONSTRAINT refresh_tokens_session_|CONSTRAINT refresh_tokens_rotation_|CREATE INDEX refresh_tokens_session_idx|CREATE INDEX refresh_tokens_replaced_idx).*\n",
        "",
        ddl,
        flags=re.M,
    )
    import psycopg

    with psycopg.connect(
        URL.replace("postgresql+psycopg://", "postgresql://"), autocommit=True
    ) as conn:
        conn.execute("CREATE SCHEMA migration_test")
        conn.execute("SET search_path TO migration_test, public")
        conn.execute(ddl)
        conn.execute(
            "INSERT INTO users(role_id,email,password_hash) SELECT id,'legacy@example.com','!' FROM roles WHERE name='user'"
        )
        conn.execute(
            "INSERT INTO refresh_tokens(user_id,token_hash,expires_at) SELECT id,'old-hash',now()+interval '1 day' FROM users"
        )
        conn.execute(
            Path("../database/migrations/003_auth_sessions.sql").read_text(
                encoding="utf-8"
            )
        )
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1
        assert conn.execute(
            "SELECT revoked_at IS NOT NULL FROM refresh_tokens"
        ).fetchone()[0]
        assert (
            conn.execute(
                "SELECT count(*) FROM information_schema.columns WHERE table_schema='migration_test' AND table_name='refresh_tokens' AND column_name='session_id'"
            ).fetchone()[0]
            == 1
        )
        conn.execute("DROP SCHEMA migration_test CASCADE")


def test_guest_schema_migrations_from_original_user_only_schema(setup):
    import re

    import psycopg

    ddl = Path("../database/ddl/001_init.sql").read_text(encoding="utf-8")
    ddl = re.sub(
        r"CREATE TABLE auth_sessions .*?(?=CREATE TABLE refresh_tokens)",
        "",
        ddl,
        flags=re.S,
    )
    ddl = re.sub(
        r"CREATE TABLE IF NOT EXISTS password_reset_tokens .*?(?=CREATE TABLE guest_sessions)",
        "",
        ddl,
        flags=re.S,
    )
    ddl = re.sub(
        r"CREATE TABLE guest_sessions .*?(?=CREATE TABLE chat_sessions)",
        "",
        ddl,
        flags=re.S,
    )
    ddl = re.sub(
        r"-- Matches backend/app/models/product.py;.*?(?=CREATE TABLE audit_logs)",
        "",
        ddl,
        flags=re.S,
    )
    ddl = re.sub(
        r"^.*(?:session_id uuid,|rotated_at timestamptz,|replaced_by_id uuid REFERENCES refresh_tokens|CONSTRAINT refresh_tokens_session_|CONSTRAINT refresh_tokens_rotation_|CREATE INDEX refresh_tokens_session_idx|CREATE INDEX refresh_tokens_replaced_idx|guest_session_id uuid REFERENCES|CONSTRAINT chat_sessions_owner_check|CONSTRAINT image_uploads_owner_check).*\n",
        "",
        ddl,
        flags=re.M,
    )
    ddl = re.sub(
        r"CREATE INDEX (?:chat_sessions|image_uploads)_guest_.*?;\n",
        "",
        ddl,
        flags=re.S,
    )
    ddl = ddl.replace(
        "user_id uuid REFERENCES users(id) ON DELETE RESTRICT",
        "user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT",
    )
    with psycopg.connect(
        URL.replace("postgresql+psycopg://", "postgresql://"), autocommit=True
    ) as conn:
        conn.execute("CREATE SCHEMA original_schema_test")
        conn.execute("SET search_path TO original_schema_test,public")
        conn.execute(ddl)
        for name in [
            "001_guest_sessions.sql",
            "002_product_image_embeddings.sql",
            "003_auth_sessions.sql",
        ]:
            conn.execute(
                Path("../database/migrations", name).read_text(encoding="utf-8")
            )
        assert (
            conn.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='original_schema_test'"
            ).fetchone()[0]
            == 13
        )
        conn.execute("DROP SCHEMA original_schema_test CASCADE")


def test_guest_expiry_and_revocation_block_search_and_upload(setup):
    with TestClient(setup.app) as client:
        result = guest(client)
        gid = UUID(result["id"])
        with setup.sessions() as db:
            db.execute(
                text("UPDATE guest_sessions SET revoked_at=now() WHERE id=:id"),
                {"id": gid},
            )
            db.commit()
        assert upload(client).status_code == 401
        assert client.get("/api/v1/auth/guest-sessions/current").status_code == 401
        client.cookies.clear()
        result = guest(client)
        gid = UUID(result["id"])
        with setup.sessions() as db:
            db.execute(
                text(
                    "UPDATE guest_sessions SET created_at=now()-interval '2 days',expires_at=now()-interval '1 day' WHERE id=:id"
                ),
                {"id": gid},
            )
            db.commit()
        assert upload(client).status_code == 401


def test_refresh_session_expiry(setup):
    with TestClient(setup.app) as client:
        access = login(client)
        with setup.sessions() as db:
            db.execute(
                text(
                    "UPDATE auth_sessions SET created_at=now()-interval '2 days',expires_at=now()-interval '1 day'"
                )
            )
            db.commit()
        assert client.post("/api/v1/auth/refresh", headers=ORIGIN).status_code == 401
        assert (
            client.get(
                "/api/v1/users/me", headers={"Authorization": "Bearer " + access}
            ).status_code
            == 401
        )


def test_uuid7_defaults_and_migration_preserves_existing_ids(setup):
    import psycopg
    from sqlalchemy.engine import make_url

    url = make_url(URL)
    with psycopg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        dbname=url.database,
        autocommit=True,
    ) as conn:
        conn.execute(
            "INSERT INTO users(id,role_id,email,password_hash) SELECT gen_random_uuid(),id,'legacy-uuid@test.example','unused' FROM roles WHERE name='user'"
        )
        before = conn.execute("SELECT id FROM users ORDER BY id").fetchall()
        conn.execute(
            "ALTER TABLE public.users ALTER COLUMN id SET DEFAULT gen_random_uuid()"
        )
        migration = Path("../database/migrations/004_uuid_v7.sql").read_text(
            encoding="utf-8"
        )
        conn.execute(migration)
        conn.execute(migration)  # repeat-safe
        assert conn.execute("SELECT id FROM users ORDER BY id").fetchall() == before
        defaults = conn.execute(
            "SELECT column_default FROM information_schema.columns WHERE table_schema='public' AND column_name='id' AND data_type='uuid'"
        ).fetchall()
        assert len(defaults) == 13
        assert all("ink_buddy_uuid_v7" in row[0] for row in defaults)
        rows = conn.execute(
            "SELECT public.ink_buddy_uuid_v7() FROM generate_series(1, 10000)"
        ).fetchall()
        values = [row[0] for row in rows]
        assert len(set(values)) == 10000
        assert all(value.version == 7 for value in values)
        milliseconds = conn.execute(
            "SELECT floor(extract(epoch FROM clock_timestamp())*1000)::bigint"
        ).fetchone()[0]
        assert all(abs((value.int >> 80) - milliseconds) < 5000 for value in values)
        generated = conn.execute(
            "INSERT INTO users(role_id,email,password_hash) SELECT id,'uuid7@test.example','unused' FROM roles WHERE name='user' RETURNING id"
        ).fetchone()[0]
        assert generated.version == 7


create_guest = guest


def test_chat_session_crud_ownership_and_soft_delete(setup):
    with TestClient(setup.app) as guest, TestClient(setup.app) as other:
        g = create_guest(guest)
        create_guest(other)
        result = guest.post("/api/v1/chat-sessions", json={}, headers=ORIGIN)
        assert result.status_code == 201, result.text
        chat = result.json()
        assert UUID(chat["id"]).version == 7 and chat["title"] == "แชตใหม่"
        path = "/api/v1/chat-sessions/" + chat["id"]
        for method in ("GET", "PATCH", "DELETE"):
            response = other.request(
                method,
                path,
                json={"title": "other"} if method == "PATCH" else None,
                headers=ORIGIN,
            )
            assert response.status_code == 404
        assert other.get(path + "/messages").status_code == 404
        assert (
            guest.patch(path, json={"title": "  สมุด  "}, headers=ORIGIN).json()["title"]
            == "สมุด"
        )
        for title in ("", "   ", "x" * 201, None):
            assert (
                guest.patch(path, json={"title": title}, headers=ORIGIN).status_code
                == 422
            )
        assert guest.get(path + "/messages").json()["items"] == []
        with setup.sessions() as db:
            db.execute(
                text(
                    "INSERT INTO chat_messages(session_id,sequence_number,role,content) VALUES(:sid,1,'user','kept')"
                ),
                {"sid": UUID(chat["id"])},
            )
            db.commit()
        assert guest.delete(path, headers=ORIGIN).status_code == 204
        assert guest.get(path).status_code == 404
        assert guest.get(path + "/messages").status_code == 404
        assert guest.delete(path, headers=ORIGIN).status_code == 404
        assert guest.get("/api/v1/chat-sessions").json()["items"] == []
        with setup.sessions() as db:
            assert (
                db.execute(
                    text("SELECT count(*) FROM chat_messages WHERE session_id=:sid"),
                    {"sid": UUID(chat["id"])},
                ).scalar_one()
                == 1
            )
            assert (
                db.execute(
                    text("SELECT image_uploads_used FROM guest_sessions WHERE id=:gid"),
                    {"gid": UUID(g["id"])},
                ).scalar_one()
                == 0
            )


def test_chat_cursor_and_message_pagination(setup):
    with TestClient(setup.app) as client:
        create_guest(client)
        chats = [
            client.post(
                "/api/v1/chat-sessions", json={"title": f"chat {n}"}, headers=ORIGIN
            ).json()
            for n in range(5)
        ]
        with setup.sessions() as db:
            db.execute(
                text(
                    "UPDATE chat_sessions SET updated_at=(SELECT max(created_at) FROM chat_sessions)"
                )
            )
            db.commit()
        found = []
        cursor = None
        while True:
            result = client.get(
                "/api/v1/chat-sessions",
                params={"limit": 2, **({"cursor": cursor} if cursor else {})},
            ).json()
            found.extend(x["id"] for x in result["items"])
            cursor = result["next_cursor"]
            if not cursor:
                break
        assert found == sorted([c["id"] for c in chats], reverse=True)
        assert len(set(found)) == 5
        sid = UUID(chats[0]["id"])
        with setup.sessions() as db:
            for n in range(1, 8):
                db.execute(
                    text(
                        "INSERT INTO chat_messages(session_id,sequence_number,role,content) VALUES(:sid,:n,'user',:content)"
                    ),
                    {"sid": sid, "n": n, "content": str(n)},
                )
            db.commit()
        path = f"/api/v1/chat-sessions/{sid}/messages"
        page = client.get(path, params={"limit": 3}).json()
        assert [m["sequence_number"] for m in page["items"]] == [5, 6, 7]
        older = client.get(
            path, params={"limit": 3, "cursor": page["next_cursor"]}
        ).json()
        assert [m["sequence_number"] for m in older["items"]] == [2, 3, 4]
        last = client.get(
            path, params={"limit": 3, "cursor": older["next_cursor"]}
        ).json()
        assert [m["sequence_number"] for m in last["items"]] == [1] and last[
            "next_cursor"
        ] is None
        assert (
            client.get(
                f"/api/v1/chat-sessions/{chats[1]['id']}/messages",
                params={"cursor": page["next_cursor"]},
            ).status_code
            == 422
        )
        for cursor in ("garbage", "W10", "bnVsbA", "a" * 1025):
            assert (
                client.get(
                    "/api/v1/chat-sessions", params={"cursor": cursor}
                ).status_code
                == 422
            )
            assert client.get(path, params={"cursor": cursor}).status_code == 422
        assert (
            client.get("/api/v1/chat-sessions", params={"limit": 101}).status_code
            == 422
        )


def test_chat_claim_and_expiry(setup):
    with TestClient(setup.app) as client:
        create_guest(client)
        chat = client.post("/api/v1/chat-sessions", json={}, headers=ORIGIN).json()
        token = login(client)
        headers = {"Authorization": "Bearer " + token, **ORIGIN}
        assert (
            client.get(
                "/api/v1/chat-sessions/" + chat["id"], headers=headers
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/v1/auth/guest-sessions/current/claim", headers=headers
            ).status_code
            == 200
        )
        assert (
            client.get(
                "/api/v1/chat-sessions/" + chat["id"], headers=headers
            ).status_code
            == 200
        )
        assert (
            client.patch(
                "/api/v1/chat-sessions/" + chat["id"],
                json={"title": "user owned"},
                headers=headers,
            ).status_code
            == 200
        )
        assert client.get("/api/v1/chat-sessions/" + chat["id"]).status_code == 401
    with TestClient(setup.app) as expired:
        guest = create_guest(expired)
        with setup.sessions() as db:
            db.execute(
                text(
                    "UPDATE guest_sessions SET created_at=now()-interval '2 days',expires_at=now()-interval '1 day' WHERE id=:gid"
                ),
                {"gid": UUID(guest["id"])},
            )
            db.commit()
        assert (
            expired.post("/api/v1/chat-sessions", json={}, headers=ORIGIN).status_code
            == 401
        )


def test_chat_claim_races_mutations(setup):
    from threading import Barrier

    from app.services.session.service import ChatSessionService

    for operation in ("create", "rename"):
        with TestClient(setup.app) as client:
            guest = create_guest(client)
            chat = client.post("/api/v1/chat-sessions", json={}, headers=ORIGIN).json()
            token = login(client)
            with setup.sessions() as db:
                user = AuthService(db, setup.settings).authenticate_user(token)
            raw = client.cookies.get(GUEST_COOKIE)
            barrier = Barrier(2)

            def mutate():
                with setup.sessions() as db:
                    principal = Principal("guest", UUID(guest["id"]))
                    barrier.wait(timeout=5)
                    try:
                        service = ChatSessionService(db)
                        if operation == "create":
                            service.create(principal, "race")
                        else:
                            service.rename(principal, UUID(chat["id"]), "race")
                        return 200
                    except ApiError as e:
                        db.rollback()
                        return e.status

            def claim_guest():
                with setup.sessions() as db:
                    barrier.wait(timeout=5)
                    return AuthService(db, setup.settings).claim(user, raw)

            with ThreadPoolExecutor(max_workers=2) as pool:
                a = pool.submit(mutate)
                b = pool.submit(claim_guest)
                assert a.result(timeout=10) in (200, 401)
                b.result(timeout=10)
            with setup.sessions() as db:
                assert (
                    db.execute(
                        text(
                            "SELECT count(*) FROM chat_sessions WHERE guest_session_id=:gid"
                        ),
                        {"gid": UUID(guest["id"])},
                    ).scalar_one()
                    == 0
                )
                assert (
                    db.execute(
                        text("SELECT user_id FROM chat_sessions WHERE id=:sid"),
                        {"sid": UUID(chat["id"])},
                    ).scalar_one()
                    == user.id
                )


def test_register_login_and_reserved_role(setup):
    with TestClient(setup.app) as client:
        data = {
            "email": "new@example.com",
            "password": "NewAccount123!",
            "display_name": "  New User  ",
        }
        assert (
            client.post("/api/v1/auth/register", json=data, headers=ORIGIN).status_code
            == 201
        )
        assert (
            client.post(
                "/api/v1/auth/register",
                json={**data, "email": "NEW@example.com"},
                headers=ORIGIN,
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/api/v1/auth/register",
                json={**data, "email": "admin-new@example.com", "role": "admin"},
                headers=ORIGIN,
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/auth/register",
                json={**data, "password": "short"},
                headers=ORIGIN,
            ).status_code
            == 422
        )
        assert client.post("/api/v1/auth/register", json=data).status_code == 403
        token = client.post(
            "/api/v1/auth/login",
            json={"email": data["email"], "password": data["password"]},
            headers=ORIGIN,
        ).json()["access_token"]
        profile = client.get(
            "/api/v1/users/me", headers={"Authorization": "Bearer " + token}
        ).json()
        assert profile["role"] == "user" and profile["display_name"] == "New User"


def test_password_reset_single_use_revokes_sessions_and_private_response(
    setup, monkeypatch
):
    from app.core.security import token_hash
    from app.services.auth.mail import Mailer

    sent = []
    monkeypatch.setattr(Mailer, "send", lambda self, message: sent.append(message))
    with TestClient(setup.app) as client:
        access = login(client)
        raw_refresh = client.cookies.get(REFRESH_COOKIE)
        existing = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "user@example.com"},
            headers=ORIGIN,
        )
        missing = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "absent@example.com"},
            headers=ORIGIN,
        )
        assert (
            existing.status_code == missing.status_code == 202
            and existing.json() == missing.json()
        )
        assert len(sent) == 1
        raw = sent[0].get_content().split("#token=")[1].split()[0]
        assert raw not in existing.text
        with setup.sessions() as db:
            row = (
                db.execute(text("SELECT * FROM password_reset_tokens")).mappings().one()
            )
            assert (
                row["token_hash"] == token_hash(raw)
                and UUID(str(row["id"])).version == 7
            )
        # Per-account cooldown returns generic 202 without another email.
        client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "user@example.com"},
            headers=ORIGIN,
        )
        assert len(sent) == 1
        payload = {"token": raw, "password": "Replacement123!"}
        assert (
            client.post(
                "/api/v1/auth/reset-password", json=payload, headers=ORIGIN
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/auth/reset-password", json=payload, headers=ORIGIN
            ).status_code
            == 400
        )
        assert (
            client.get(
                "/api/v1/users/me", headers={"Authorization": "Bearer " + access}
            ).status_code
            == 401
        )
        client.cookies.set(REFRESH_COOKIE, raw_refresh)
        assert client.post("/api/v1/auth/refresh", headers=ORIGIN).status_code == 401
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"email": "user@example.com", "password": PASSWORD},
                headers=ORIGIN,
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"email": "user@example.com", "password": payload["password"]},
                headers=ORIGIN,
            ).status_code
            == 200
        )
        assert len(sent) == 2 and payload["password"] not in sent[-1].get_content()


def test_password_reset_expiry_replacement_and_concurrency(setup, monkeypatch):
    from app.services.auth.mail import Mailer

    sent = []
    monkeypatch.setattr(Mailer, "send", lambda self, message: sent.append(message))
    with TestClient(setup.app) as client:
        client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "user@example.com"},
            headers=ORIGIN,
        )
        raw = sent[-1].get_content().split("#token=")[1].split()[0]
        with setup.sessions() as db:
            db.execute(
                text(
                    "UPDATE password_reset_tokens SET created_at=now()-interval '2 hours',expires_at=now()-interval '1 hour'"
                )
            )
            db.commit()
        assert (
            client.post(
                "/api/v1/auth/reset-password",
                json={"token": raw, "password": "UpdatedPassword123!"},
                headers=ORIGIN,
            ).status_code
            == 400
        )
        client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "user@example.com"},
            headers=ORIGIN,
        )
        raw_new = sent[-1].get_content().split("#token=")[1].split()[0]
        assert (
            client.post(
                "/api/v1/auth/reset-password",
                json={"token": raw, "password": "UpdatedPassword123!"},
                headers=ORIGIN,
            ).status_code
            == 400
        )
        from threading import Barrier

        barrier = Barrier(2)

        def consume():
            with setup.sessions() as db:
                barrier.wait(timeout=5)
                try:
                    AuthService(db, setup.settings).reset_password(
                        raw_new, "Concurrent123!"
                    )
                    return 200
                except ApiError as e:
                    db.rollback()
                    return e.status

        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(consume)
            b = pool.submit(consume)
            assert sorted([a.result(timeout=10), b.result(timeout=10)]) == [200, 400]


def test_password_reset_migration_repeat_safe(setup):
    import psycopg
    from sqlalchemy.engine import make_url

    url = make_url(URL)
    with psycopg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        dbname=url.database,
        autocommit=True,
    ) as db:
        before = db.execute("SELECT id FROM users ORDER BY id").fetchall()
        db.execute("DROP TABLE password_reset_tokens")
        migration = Path(
            "../database/migrations/005_register_password_reset.sql"
        ).read_text(encoding="utf-8")
        db.execute(migration)
        db.execute(migration)
        assert db.execute("SELECT id FROM users ORDER BY id").fetchall() == before
        assert (
            db.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
            ).fetchone()[0]
            == 14
        )


def message_setup(setup):
    with setup.sessions() as db:
        guest, raw, _ = AuthService(db, setup.settings).create_guest(None)
        principal = Principal("guest", guest.id)
        from app.services.session.service import ChatSessionService

        chat = ChatSessionService(db).create(principal, None)
        product = db.execute(
            text(
                "INSERT INTO products(sku,name,category,brand,description,price,currency,source_ref) VALUES('CHAT-PEN','ปากกาเจล Ink','gel_pen','Ink','จดโน้ต',50,'THB','https://example.test/pen') RETURNING id"
            )
        ).scalar_one()
        db.commit()
    return principal, chat.id, raw, product


def test_conversational_rag_price_context_variants_and_replay(setup):
    import json
    from app.core.identifiers import uuid7
    from app.schemas.session import SendMessageRequest
    from app.services.session.message_service import MessageService
    from app.services.session.openrouter_adapter import OpenRouterCatalogAdapter
    principal,sid,_,_=message_setup(setup)
    settings=setup.settings.model_copy(update={'chat_adapter':'openrouter_catalog'})
    ids={}
    with setup.sessions() as db:
        db.execute(text('DELETE FROM products'))
        for label,name,price,attrs in [
            ('blue1','ปากกาเจล รุ่น B1 หมึกสีน้ำเงิน',10,{'unit':'ด้าม','model_family':'B1'}),
            ('blue2','ปากกาเจล รุ่น B2 หมึกสีน้ำเงิน',20,{'unit':'ด้าม','model_family':'B2','price_source_ref':'https://example.test/price','price_tax_basis':'excludes_vat'}),
            ('blue3','ปากกาเจล รุ่น B3 หมึกสีน้ำเงิน',30,{'unit':'ด้าม','model_family':'B3'}),
            ('red2','ปากกาเจล รุ่น B2 หมึกสีแดง',20,{'unit':'ด้าม','model_family':'B2'}),
            ('purple','ปากกาเจล รุ่น B4 หมึกสีม่วง',1,{'unit':'ด้าม'}),
            ('unknown','ปากกาเจล รุ่น B5 หมึกสีน้ำเงิน',None,{'unit':'ด้าม'}),
            ('pack','ปากกาเจล รุ่น B6 หมึกสีน้ำเงิน แพ็ค 12',5,{'price_selling_unit':'แพ็ค 12 ด้าม'})]:
            ids[label]=db.execute(text("INSERT INTO products(name,category,brand,price,currency,attributes) VALUES(:name,'gel_pen','Test',:price,'THB',CAST(:attrs AS jsonb)) RETURNING id"),{'name':name,'price':price,'attrs':json.dumps(attrs)}).scalar_one()
        db.commit()
    class Client:
        calls=0
        def chat(self,model,messages,**kwargs):
            self.calls+=1
            catalog=json.loads(messages[1]['content'])['catalog']
            recommendations=[{'product_id':p['product_id'],'evidence_ids':[next(iter(p['evidence']))]} for p in reversed(catalog)]
            return {'model':'qwen/qwen3-14b','done_reason':'stop','message':{'content':json.dumps({'recommendations':recommendations})}}
    client=Client();adapter=OpenRouterCatalogAdapter(settings,client=client)
    def send(content,rid=None):
        with setup.sessions() as db:return MessageService(db,settings,adapter).send(principal,sid,SendMessageRequest(content=content,client_request_id=rid or uuid7()))
    rid=uuid7();first=send('ปากกาหมึกน้ำเงิน สามรุ่นถูกที่สุด และมีสีอื่นไหม',rid)
    refs=first.assistant_message.product_refs
    assert [r.id for r in refs]==[ids['blue1'],ids['blue2'],ids['blue3']]
    assert [r.price for r in refs]==[10,20,30]
    assert [r.id for r in refs[1].variants]==[ids['red2']]
    assert refs[1].price_source_ref=='https://example.test/price'
    assert first.assistant_message.content.index('ปากกาเจล รุ่น B1')<first.assistant_message.content.index('รุ่นนี้มี')
    assert send('ปากกาหมึกน้ำเงิน สามรุ่นถูกที่สุด และมีสีอื่นไหม',rid)==first and client.calls==1
    second=send('ตัวที่สองราคาเท่าไร')
    assert [r.id for r in second.assistant_message.product_refs]==[ids['blue2']]
    assert '20 บาท' in second.assistant_message.content
    third=send('รุ่นนี้มีสีแดงไหม')
    assert [r.id for r in third.assistant_message.product_refs[0].variants]==[ids['red2']]
    pack=send('ปากกาหมึกน้ำเงิน ขอหนึ่งรุ่นถูกที่สุดต่อแพ็ค')
    assert pack.assistant_message.product_refs[0].id==ids['pack']
    assert pack.assistant_message.product_refs[0].pack_quantity==12
    descending=send('ปากกาหมึกน้ำเงิน สามรุ่นแพงที่สุด')
    assert [r.price for r in descending.assistant_message.product_refs]==[30,20,10]
    shortage=send('ปากกาหมึกน้ำเงิน สามรุ่นถูกที่สุด ไม่เกิน 15 บาท')
    assert [r.id for r in shortage.assistant_message.product_refs]==[ids['blue1']]
    assert 'พบเพียง 1 รายการ' in shortage.assistant_message.content
    with setup.sessions() as db:
        assert db.execute(text('SELECT count(*) FROM chat_messages')).scalar_one()==12


def test_price_filter_runs_before_keyword_candidate_limit(setup):
    from app.services.product.text_search import CatalogTextSearch
    with setup.sessions() as db:
        db.execute(text("INSERT INTO products(name,category,price,currency) SELECT 'ปากกาเจลไม่มีราคา','gel_pen',NULL,'THB' FROM generate_series(1,25)"))
        db.execute(text("INSERT INTO products(name,category,price,currency) VALUES('ปากกาเจลมีราคา','gel_pen',25,'THB')"))
        db.commit()
        rows,_=CatalogTextSearch(db).search('ปากกาเจลราคาเท่าไร',limit=5,requires_price=True)
        assert len(rows)==1 and rows[0]['price']==25

@pytest.mark.parametrize('invalid',[False,True])
def test_rag_message_api_controlled_evidence_and_replay(setup,invalid):
    import json
    from fastapi import Depends
    from app.api.v1.session.routes import message_service
    from app.services.session.message_service import MessageService
    from app.services.session.openrouter_adapter import OpenRouterCatalogAdapter
    from app.core.identifiers import uuid7
    principal,sid,raw,pid=message_setup(setup)
    settings=setup.settings.model_copy(update={'chat_adapter':'openrouter_catalog'})
    class Client:
        calls=0
        def chat(self,model,messages,**kwargs):
            self.calls+=1
            context=json.loads(messages[1]['content'])['catalog'][0]
            evidence=list(context['evidence'])[0]
            content={'recommendations':[{'product_id':context['product_id'],'evidence_ids':['foreign_evidence' if invalid else evidence]}]}
            return {'model':'qwen/qwen3-14b','done_reason':'stop','message':{'content':json.dumps(content)}}
    fake=Client()
    def service(db=Depends(get_db)):
        return MessageService(db,settings,OpenRouterCatalogAdapter(settings,client=fake))
    setup.app.dependency_overrides[message_service]=service
    payload={'content':'ปากกาเจล ไม่เกิน 100 บาท','client_request_id':str(uuid7())}
    with TestClient(setup.app) as client:
        client.cookies.set(GUEST_COOKIE,raw)
        result=client.post(f'/api/v1/chat-sessions/{sid}/messages',json=payload,headers=ORIGIN)
        if invalid:
            assert result.status_code==502 and result.json()['error']['code']=='INVALID_ANSWER'
        else:
            assert result.status_code==201,result.text
            assert result.json()['assistant_message']['model_name']=='qwen/qwen3-14b'
            assert result.json()['assistant_message']['product_refs'][0]['id']==str(pid)
            replay=client.post(f'/api/v1/chat-sessions/{sid}/messages',json=payload,headers=ORIGIN)
            assert replay.json()==result.json() and fake.calls==1
    with setup.sessions() as db:
        assert db.execute(text('SELECT count(*) FROM chat_messages WHERE session_id=:sid'),{'sid':sid}).scalar_one()==(0 if invalid else 2)


def test_message_api_replay_validation_ownership(setup):
    from app.core.identifiers import uuid7

    principal, sid, raw, product = message_setup(setup)
    payload = {
        "content": "  ปากกาเจลไม่เกิน 100 บาท  ",
        "client_request_id": str(uuid7()),
    }
    with TestClient(setup.app) as client:
        client.cookies.set(GUEST_COOKIE, raw)
        result = client.post(
            f"/api/v1/chat-sessions/{sid}/messages", json=payload, headers=ORIGIN
        )
        assert result.status_code == 201, result.text
        data = result.json()
        assert data["user_message"]["sequence_number"] == 1
        assert data["assistant_message"]["sequence_number"] == 2
        assert data["assistant_message"]["product_refs"][0]["id"] == str(product)
        assert (
            client.post(
                f"/api/v1/chat-sessions/{sid}/messages", json=payload, headers=ORIGIN
            ).json()
            == data
        )
        assert (
            client.post(
                f"/api/v1/chat-sessions/{sid}/messages",
                json={**payload, "content": "สมุด"},
                headers=ORIGIN,
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/api/v1/chat-sessions/{sid}/messages",
                json={**payload, "image_id": str(product)},
                headers=ORIGIN,
            ).status_code
            == 409
        )
        with setup.sessions() as db:
            other, token, _ = AuthService(db, setup.settings).create_guest(None)
        client.cookies.set(GUEST_COOKIE, token)
        assert (
            client.post(
                f"/api/v1/chat-sessions/{sid}/messages", json=payload, headers=ORIGIN
            ).status_code
            == 404
        )
    with setup.sessions() as db:
        assert db.execute(text("SELECT COUNT(*) FROM chat_messages")).scalar_one() == 2


def test_message_search_budget_unknown_price_and_sql(setup):
    from app.services.product.text_search import CatalogTextSearch

    message_setup(setup)
    with setup.sessions() as db:
        db.execute(
            text(
                "INSERT INTO products(name,category) VALUES('ปากกาเจล Unknown','gel_pen')"
            )
        )
        db.commit()
        search = CatalogTextSearch(db)
        assert len(search.search("ปากกาเจลไม่เกิน 100 บาท")[0]) == 1
        assert not search.search("ปากกาเจลไม่เกิน 10 บาท")[0]
        assert len(search.search("Ink")[0]) == 1
        assert not search.search("'; DROP TABLE products; --")[0]
        assert not search.search("สมุดราคาถูก")[1]


@pytest.mark.parametrize("adapter_mode", ["catalog_template", "openrouter_catalog"])
def test_message_concurrency_and_duplicate(setup, adapter_mode):
    setup.settings=setup.settings.model_copy(update={"chat_adapter":adapter_mode})
    from threading import Barrier

    from app.core.identifiers import uuid7
    from app.schemas.session import SendMessageRequest
    from app.services.session.adapter import CatalogTemplateAdapter
    from app.services.session.message_service import MessageService

    principal, sid, _, _ = message_setup(setup)

    def run_pair(same):
        barrier = Barrier(2)

        class Adapter(CatalogTemplateAdapter):
            def answer(self, request):
                barrier.wait(timeout=5)
                return super().answer(request)

        rid = uuid7()

        def send(i):
            body = SendMessageRequest(
                content="ปากกาเจล", client_request_id=rid if same else uuid7()
            )
            with setup.sessions() as db:
                try:
                    return (
                        MessageService(db, setup.settings, Adapter())
                        .send(principal, sid, body)
                        .user_message.id
                    )
                except ApiError as e:
                    return e.status

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(send, [0, 1]))

    results = run_pair(True)
    assert results[0] == results[1]
    results = run_pair(False)
    assert results.count(409) == 1
    with setup.sessions() as db:
        assert db.execute(text("SELECT COUNT(*) FROM chat_messages")).scalar_one() == 4


@pytest.mark.parametrize(
    "event", ["claim", "delete", "expire", "failure", "invalid", "timeout"]
)
@pytest.mark.parametrize("adapter_mode", ["catalog_template", "openrouter_catalog"])
def test_message_failure_and_owner_change_leave_no_history(setup, event, adapter_mode):
    setup.settings=setup.settings.model_copy(update={"chat_adapter":adapter_mode})
    import time

    from app.core.identifiers import uuid7
    from app.schemas.session import SendMessageRequest
    from app.services.session.adapter import AnswerOutput, CatalogTemplateAdapter
    from app.services.session.message_service import MessageService

    principal, sid, raw, product = message_setup(setup)

    class Adapter(CatalogTemplateAdapter):
        def answer(self, request):
            if event == "failure":
                raise RuntimeError("test")
            if event == "invalid":
                return AnswerOutput("answer", (uuid7(),), "test")
            if event == "timeout":
                time.sleep(0.1)
                return super().answer(request)
            with setup.sessions() as other:
                if event == "claim":
                    AuthService(other, setup.settings).claim(
                        Principal("user", setup.ids["user"]), raw
                    )
                elif event == "delete":
                    other.execute(
                        text(
                            "UPDATE chat_sessions SET deleted_at=clock_timestamp() WHERE id=:id"
                        ),
                        {"id": sid},
                    )
                    other.commit()
                elif event == "expire":
                    other.execute(
                        text(
                            "UPDATE guest_sessions SET created_at=now()-interval '2 days',expires_at=now()-interval '1 day' WHERE id=:id"
                        ),
                        {"id": principal.id},
                    )
                    other.commit()
            return super().answer(request)

    settings = (
        setup.settings.model_copy(update={"chat_timeout_seconds": 0.02})
        if event == "timeout"
        else setup.settings
    )
    with setup.sessions() as db:
        with pytest.raises(ApiError) as err:
            MessageService(db, settings, Adapter()).send(
                principal,
                sid,
                SendMessageRequest(content="ปากกาเจล", client_request_id=uuid7()),
            )
        assert err.value.status in [401, 404, 502, 504]
    with setup.sessions() as db:
        assert db.execute(text("SELECT COUNT(*) FROM chat_messages")).scalar_one() == 0


@pytest.mark.parametrize("adapter_mode", ["catalog_template", "openrouter_catalog"])
def test_message_pair_rolls_back_on_insert_failure(setup, monkeypatch, adapter_mode):
    setup.settings=setup.settings.model_copy(update={"chat_adapter":adapter_mode})
    from app.core.identifiers import uuid7
    from app.schemas.session import SendMessageRequest
    from app.services.session.message_service import MessageService
    from app.services.session.adapter import CatalogTemplateAdapter

    principal, sid, _, _ = message_setup(setup)
    with setup.sessions() as db:
        execute = db.execute

        def fail(statement, params=None, *args, **kwargs):
            if params and params.get("role") == "assistant":
                raise RuntimeError("DB failure")
            return execute(statement, params, *args, **kwargs)

        monkeypatch.setattr(db, "execute", fail)
        with pytest.raises(ApiError) as error:
            MessageService(db, setup.settings, CatalogTemplateAdapter()).send(
                principal,
                sid,
                SendMessageRequest(content="ปากกาเจล", client_request_id=uuid7()),
            )
    assert error.value.status == 500
    with setup.sessions() as db:
        assert db.execute(text("SELECT COUNT(*) FROM chat_messages")).scalar_one() == 0


def test_message_migration_repeat_safe(setup):
    import psycopg
    from sqlalchemy.engine import make_url

    url = make_url(URL)
    with psycopg.connect(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
        autocommit=True,
    ) as db:
        db.execute("ALTER TABLE chat_messages DROP COLUMN client_request_id CASCADE")
        sql = Path("../database/migrations/006_chat_messages.sql").read_text()
        db.execute(sql)
        db.execute(sql)
        assert (
            db.execute(
                "SELECT COUNT(*) FROM pg_indexes WHERE indexname='chat_messages_request_uq'"
            ).fetchone()[0]
            == 1
        )


@pytest.mark.parametrize("event", ["logout", "access_expiry", "inactive"])
@pytest.mark.parametrize("adapter_mode", ["catalog_template", "openrouter_catalog"])
def test_message_user_credential_rechecked_after_answer(setup, event, adapter_mode):
    setup.settings=setup.settings.model_copy(update={"chat_adapter":adapter_mode})
    import time
    from dataclasses import replace

    from app.core.identifiers import uuid7
    from app.schemas.session import SendMessageRequest
    from app.services.session.adapter import CatalogTemplateAdapter
    from app.services.session.message_service import MessageService
    from app.services.session.service import ChatSessionService

    with setup.sessions() as db:
        token, refresh, _ = AuthService(db, setup.settings).login(
            "user@example.com", PASSWORD
        )
        principal = AuthService(db, setup.settings).authenticate_user(
            token.access_token
        )
        if event == "access_expiry":
            principal = replace(
                principal, access_expires_at=utcnow() + timedelta(seconds=0.1)
            )
        chat = ChatSessionService(db).create(principal, None)

        # Ensure this revocation race enters inference, not an empty-catalog policy.
        db.execute(text("INSERT INTO products(name,category,price,currency) VALUES('ปากกาเจล race','gel_pen',50,'THB')"))
        db.commit()

    class Adapter(CatalogTemplateAdapter):
        def answer(self, request):
            if event == "access_expiry":
                time.sleep(0.15)
            else:
                with setup.sessions() as db:
                    if event == "logout":
                        AuthService(db, setup.settings).logout(refresh)
                    else:
                        db.execute(
                            text("UPDATE users SET is_active=false WHERE id=:id"),
                            {"id": principal.id},
                        )
                        db.commit()
            return super().answer(request)

    with setup.sessions() as db:
        with pytest.raises(ApiError) as error:
            MessageService(db, setup.settings, Adapter()).send(
                principal,
                chat.id,
                SendMessageRequest(content="ปากกา", client_request_id=uuid7()),
            )
        assert error.value.status == 401
    with setup.sessions() as db:
        assert db.execute(text("SELECT COUNT(*) FROM chat_messages")).scalar_one() == 0


def test_vision_text_message_private_preview_and_replay(setup):
    from fastapi import Depends
    from app.core.identifiers import uuid7
    from app.api.v1.session.routes import message_service
    from app.services.session.message_service import MessageService
    from app.ai.prompts.vision_prompt import ImageAnalysis,Intent
    principal,sid,raw,pid=message_setup(setup)
    with setup.sessions() as db:
        image=setup.vision.upload_image(db,principal,image_bytes()).id
    class Vision:
        calls=0
        def analyze(self,img,prompt,retries=0):
            self.calls+=1
            assert prompt=='มีสินค้านี้ไหม' and img.size==(64,64) and retries==0
            return ImageAnalysis(is_stationery=True,intent=Intent.FIND_SIMILAR,category_guess='gel_pen',brand_text='Ink',description='ปากกาเจล')
    vision=Vision()
    def service(db=Depends(get_db)):return MessageService(db,setup.settings,vision_service=vision)
    setup.app.dependency_overrides[message_service]=service
    payload={'image_id':str(image),'client_request_id':str(uuid7())}
    with TestClient(setup.app) as client:
        client.cookies.set(GUEST_COOKIE,raw)
        content=client.get(f'/api/v1/images/{image}/content')
        assert content.status_code==200 and content.headers['content-type']=='image/png'
        assert content.headers['cache-control']=='private, no-store'
        assert Image.open(io.BytesIO(content.content)).size==(64,64)
        first=client.post(f'/api/v1/chat-sessions/{sid}/messages',json=payload,headers=ORIGIN)
        assert first.status_code==201,first.text
        pair=first.json();assert pair['user_message']['image_id']==str(image)
        assert pair['assistant_message']['model_name']=='vision_catalog'
        ref=pair['assistant_message']['product_refs'][0]
        assert ref['id']==str(pid) and ref['match_type']=='similar' and ref['match_method']=='vision_text_catalog'
        assert ref['match_score'] is None # no fake probability from keyword/RRF score
        assert client.post(f'/api/v1/chat-sessions/{sid}/messages',json=payload,headers=ORIGIN).json()==pair
        assert vision.calls==1
        conflict=client.post(f'/api/v1/chat-sessions/{sid}/messages',json={**payload,'image_id':str(uuid7())},headers=ORIGIN)
        assert conflict.status_code==409
        with setup.sessions() as db:
            other,token,_=AuthService(db,setup.settings).create_guest(None)
        client.cookies.set(GUEST_COOKIE,token)
        assert client.get(f'/api/v1/images/{image}/content').status_code==404
        from app.services.session.service import ChatSessionService
        with setup.sessions() as db:other_chat=ChatSessionService(db).create(Principal('guest',other.id),None)
        assert client.post(f'/api/v1/chat-sessions/{other_chat.id}/messages',json={**payload,'client_request_id':str(uuid7())},headers=ORIGIN).status_code==404
    with setup.sessions() as db:
        assert db.execute(text('SELECT count(*) FROM chat_messages')).scalar_one()==2
        assert db.execute(text('SELECT image_uploads_used FROM guest_sessions WHERE id=:id'),{'id':principal.id}).scalar_one()==1


@pytest.mark.parametrize('event',['claim','delete','logout','failure','non_stationery'])
def test_vision_message_rechecks_and_rolls_back(setup,event):
    from app.core.identifiers import uuid7
    from app.schemas.session import SendMessageRequest
    from app.services.session.message_service import MessageService
    from app.ai.prompts.vision_prompt import ImageAnalysis,Intent
    principal,sid,raw,_=message_setup(setup)
    if event=='logout':
        from app.services.session.service import ChatSessionService
        with setup.sessions() as db:
            access,refresh,_=AuthService(db,setup.settings).login('user@example.com',PASSWORD)
            principal=AuthService(db,setup.settings).authenticate_user(access.access_token)
            sid=ChatSessionService(db).create(principal,None).id
    with setup.sessions() as db:image=setup.vision.upload_image(db,principal,image_bytes()).id
    class Vision:
        def analyze(self,img,prompt,retries=0):
            if event=='failure':raise RuntimeError('fake provider failure')
            if event in ('claim','delete','logout'):
                with setup.sessions() as db:
                    if event=='claim':AuthService(db,setup.settings).claim(Principal('user',setup.ids['user']),raw)
                    elif event=='logout':AuthService(db,setup.settings).logout(refresh)
                    else:
                        db.execute(text('UPDATE chat_sessions SET deleted_at=now() WHERE id=:id'),{'id':sid});db.commit()
            return ImageAnalysis(is_stationery=event!='non_stationery',intent=Intent.FIND_SIMILAR,category_guess='gel_pen',description='ปากกา')
    with setup.sessions() as db:
        call=lambda:MessageService(db,setup.settings,vision_service=Vision()).send(principal,sid,SendMessageRequest(image_id=image,client_request_id=uuid7()))
        if event=='non_stationery':assert not call().assistant_message.product_refs
        else:
            with pytest.raises(ApiError) as error:call()
            assert error.value.status in (401,404,502)
    with setup.sessions() as db:
        assert db.execute(text('SELECT count(*) FROM chat_messages')).scalar_one()==(2 if event=='non_stationery' else 0)
