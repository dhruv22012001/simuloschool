import jwt as pyjwt
import pytest

from app.core.auth import create_access_token, decode_token, hash_password, verify_password
from app.models.base import Role
from app.models.user import User


def _user() -> User:
    return User(
        id=42,
        name="Test",
        email="t@example.com",
        password_hash=hash_password("pw"),
        role=Role.admin,
    )


def test_password_hash_round_trip():
    hashed = hash_password("s3cret")
    assert hashed != "s3cret"
    assert verify_password("s3cret", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_round_trip():
    token = create_access_token(_user())
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"


def test_jwt_wrong_secret_rejected():
    token = create_access_token(_user())
    with pytest.raises(pyjwt.InvalidTokenError):
        pyjwt.decode(token, "other-secret-0123456789abcdef0123456789", algorithms=["HS256"])


def test_protected_route_rejects_missing_and_bad_tokens(client):
    assert client.get("/videos").status_code == 401
    assert client.get("/videos", headers={"Authorization": "Bearer nonsense"}).status_code == 401
