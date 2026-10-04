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

from app.ai.prompts.vision_prompt import MatchLevel
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
from scripts.cleanup_guests import cleanup

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
            return SimpleNamespace(
                products=[],
                analysis=None,
                match_level=MatchLevel.NONE,
                path="fast",
                timings_s={},
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
    settings = setup.settings.model_copy(update={"app_environment": "production"})
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
        conn.execute("INSERT INTO users(id,role_id,email,password_hash) SELECT gen_random_uuid(),id,'legacy-uuid@test.example','unused' FROM roles WHERE name='user'")
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
        assert len(defaults) == 12
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
