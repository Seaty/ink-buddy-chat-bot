import pytest
from app.core.password_policy import validate_new_password
from app.schemas.auth import LoginRequest, RegisterRequest, ResetPasswordRequest


@pytest.mark.parametrize(
    "password", ["Abcdefghij1!", "A" + "b" * 21 + "1!", "Abcdef123!ไทย"]
)
def test_valid_password(password):
    assert validate_new_password(password) == password
    RegisterRequest(email="user@example.com", password=password)
    ResetPasswordRequest(token="x" * 43, password=password)


@pytest.mark.parametrize(
    "password",
    [
        "Abcdefghi1!",
        "A" + "b" * 22 + "1!",
        "abcdefghij1!",
        "ABCDEFGHIJ1!",
        "Abcdefghijk!",
        "Abcdefghij12",
        "Abcdefghi1! ",
        "Abcdefghi1!\t",
        "Abcdefghi1!\n",
        "Abcdefghi1!\u00a0",
        "Abcdefghi12ไทย",
    ],
)
def test_invalid_password(password):
    with pytest.raises(ValueError):
        validate_new_password(password)
    with pytest.raises(ValueError):
        RegisterRequest(email="user@example.com", password=password)
    with pytest.raises(ValueError):
        ResetPasswordRequest(token="x" * 43, password=password)


def test_login_keeps_existing_password_compatibility():
    LoginRequest(email="user@example.com", password="legacy password")
