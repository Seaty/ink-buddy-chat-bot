"""Scaffolds must be visible, honest about readiness, and perform no real work."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

ID = "123e4567-e89b-42d3-a456-426614174000"
CASES = [
    ("POST", "/auth/login", {"email": "guest@example.com", "password": "example"}),
    ("POST", "/auth/refresh", None),
    ("POST", "/auth/logout", None),
    ("POST", "/auth/guest-sessions", None),
    ("GET", "/auth/guest-sessions/current", None),
    ("POST", "/auth/guest-sessions/current/claim", None),
    ("GET", "/users/me", None),
    ("PATCH", "/users/me", {"display_name": "Example"}),
    ("POST", "/chat-sessions", {}),
    ("GET", "/chat-sessions", None),
    ("GET", f"/chat-sessions/{ID}", None),
    ("DELETE", f"/chat-sessions/{ID}", None),
    ("GET", f"/chat-sessions/{ID}/messages", None),
    ("POST", f"/chat-sessions/{ID}/messages", {"content": "Find a pen"}),
    ("GET", f"/images/{ID}", None),
    ("DELETE", f"/images/{ID}", None),
    ("GET", "/products", None),
    ("GET", f"/products/{ID}", None),
    ("GET", "/ready", None),
]


@pytest.mark.parametrize("method,path,body", CASES)
def test_scaffold_is_not_a_fake_success(method, path, body):
    with TestClient(app) as client:
        response = client.request(method, "/api/v1" + path, json=body)
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "NOT_IMPLEMENTED"


def test_openapi_marks_all_scaffolds():
    operations = [operation for item in app.openapi()["paths"].values()
                  for method, operation in item.items() if method in {"get", "post", "patch", "delete"}]
    assert len(operations) == 25  # 19 scaffolds + 6 implemented (incl. image analysis and OCR)
    scaffolds = [operation for operation in operations
                 if operation.get("x-implementation-status") == "scaffold"]
    assert len(scaffolds) == 19
    assert all("501" in operation["responses"] for operation in scaffolds)


def test_message_requires_text_or_image():
    with TestClient(app) as client:
        response = client.post(f"/api/v1/chat-sessions/{ID}/messages", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
