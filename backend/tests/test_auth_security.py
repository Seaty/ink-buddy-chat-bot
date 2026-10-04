"""Security configuration and default-deny route coverage independent of DB."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.identifiers import uuid7
from app.core.security import (
    access_token,
    decode_access,
    hash_password,
    utcnow,
    verify_password,
)
from app.main import create_app

SECRET = "test-only-signing-key-never-use-in-production-12345"


def test_signing_secret_is_required():
    app = create_app(Settings(_env_file=None, auth_jwt_secret=None))
    with pytest.raises(RuntimeError, match="AUTH_JWT_SECRET"):
        with TestClient(app):
            pass


def test_missing_policy_fails_startup():
    app = create_app(Settings(_env_file=None, auth_jwt_secret=SECRET))

    @app.get("/api/v1/unclassified")
    def unclassified():
        return {}

    with pytest.raises(RuntimeError, match="Missing access policy"):
        with TestClient(app):
            pass


def test_memory_limiter_refuses_multiple_workers():
    settings = Settings(_env_file=None, auth_jwt_secret=SECRET, auth_workers=2)
    with pytest.raises(RuntimeError, match="shared"):
        settings.validate_auth()


def test_password_roundtrip_and_invalid_hash():
    hashed = hash_password("a long example password")
    assert hashed.startswith("$argon2id$")
    assert verify_password("a long example password", hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password("anything", "!")


def test_access_claims_and_schema_security():
    settings = Settings(_env_file=None, auth_jwt_secret=SECRET)
    uid, sid = uuid7(), uuid7()
    token, seconds = access_token(settings, uid, sid, utcnow() + timedelta(days=7))
    assert 898 <= seconds <= 900 and decode_access(settings, token) == (uid, sid)
    schema = create_app(settings).openapi()
    assert all(
        "x-access-policy" in op
        for item in schema["paths"].values()
        for op in item.values()
    )
    assert schema["paths"]["/api/v1/auth/guest-sessions/current/claim"]["post"][
        "security"
    ] == [{"UserBearer": [], "GuestCookie": []}]
    assert schema["paths"]["/api/v1/health"]["get"]["security"] == []
    assert len(schema["components"]["securitySchemes"]) == 3
