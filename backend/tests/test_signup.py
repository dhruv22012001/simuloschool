"""Public student self-registration."""

import sqlalchemy as sa

from app.core.auth import decode_token
from app.models.base import Role
from app.models.user import User

VALID = {
    "name": "Aarav Sharma",
    "email": "aarav@example.com",
    "password": "correct-horse-battery",
}


def _signup(client, **overrides):
    return client.post("/auth/signup", json={**VALID, **overrides})


# ------------------------------------------------------------- happy path ----


def test_signup_creates_a_student(db_client, db):
    resp = _signup(db_client)
    assert resp.status_code == 201

    user = db.scalar(sa.select(User).where(User.email == "aarav@example.com"))
    assert user is not None
    assert user.role == Role.student
    assert user.name == "Aarav Sharma"


def test_signup_returns_a_usable_token(db_client, db):
    body = _signup(db_client).json()
    assert body["role"] == "student"
    assert body["name"] == "Aarav Sharma"

    payload = decode_token(body["access_token"])
    assert payload["role"] == "student"
    # The token works immediately — no separate login step.
    me = db_client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["role"] == "student"


def test_password_is_hashed_not_stored(db_client, db):
    _signup(db_client)
    user = db.scalar(sa.select(User).where(User.email == "aarav@example.com"))
    assert user.password_hash != VALID["password"]
    assert VALID["password"] not in user.password_hash


def test_can_log_in_after_signing_up(db_client):
    _signup(db_client)
    resp = db_client.post(
        "/auth/login", json={"email": VALID["email"], "password": VALID["password"]}
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "student"


def test_parent_email_is_optional_and_stored(db_client, db):
    _signup(db_client, parent_email="parent@example.com")
    user = db.scalar(sa.select(User).where(User.email == "aarav@example.com"))
    assert user.parent_email == "parent@example.com"


def test_parent_email_defaults_to_none(db_client, db):
    _signup(db_client)
    assert db.scalar(sa.select(User).where(User.email == "aarav@example.com")).parent_email is None


def test_name_and_email_are_trimmed(db_client, db):
    _signup(db_client, name="  Aarav  ", email="  Aarav@Example.COM ")
    user = db.scalar(sa.select(User).where(User.email == "aarav@example.com"))
    assert user is not None
    assert user.name == "Aarav"


# ------------------------------------------------- privilege escalation ----


def test_role_in_body_cannot_create_an_admin(db_client, db):
    """The security case: a crafted request must not mint an admin."""
    resp = db_client.post("/auth/signup", json={**VALID, "role": "admin"})
    assert resp.status_code == 201
    assert resp.json()["role"] == "student"
    assert db.scalar(sa.select(User).where(User.email == VALID["email"])).role == Role.student


def test_signed_up_user_cannot_reach_admin_routes(db_client):
    token = _signup(db_client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert db_client.get("/admin/videos", headers=headers).status_code == 403
    assert db_client.post("/admin/videos", headers=headers).status_code == 403


# ------------------------------------------------------------ duplicates ----


def test_duplicate_email_is_rejected(db_client):
    _signup(db_client)
    resp = _signup(db_client)
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


def test_duplicate_is_case_insensitive(db_client, db):
    """Otherwise Alice@x.com and alice@x.com become two accounts."""
    _signup(db_client, email="aarav@example.com")
    resp = _signup(db_client, email="AARAV@EXAMPLE.COM")
    assert resp.status_code == 409
    assert len(db.scalars(sa.select(User)).all()) == 1


def test_signup_cannot_hijack_the_admin_address(db_client, admin):
    """Registering an existing admin's address must not overwrite it."""
    resp = _signup(db_client, email=admin.email)
    assert resp.status_code == 409


# ------------------------------------------------------------ validation ----


def test_short_password_is_rejected(db_client):
    assert _signup(db_client, password="short").status_code == 422


def test_overlong_password_is_rejected(db_client):
    """bcrypt truncates past 72 bytes — reject instead of silently ignoring."""
    assert _signup(db_client, password="x" * 200).status_code == 422


def test_invalid_email_is_rejected(db_client):
    assert _signup(db_client, email="not-an-email").status_code == 422


def test_blank_name_is_rejected(db_client):
    assert _signup(db_client, name="").status_code == 422


def test_invalid_parent_email_is_rejected(db_client):
    assert _signup(db_client, parent_email="nope").status_code == 422


def test_missing_fields_are_rejected(db_client):
    assert db_client.post("/auth/signup", json={"email": "a@b.com"}).status_code == 422


# ------------------------------------------------------ login normalizing ----


def test_login_is_case_insensitive_on_email(db_client):
    _signup(db_client, email="aarav@example.com")
    resp = db_client.post(
        "/auth/login", json={"email": "Aarav@Example.com", "password": VALID["password"]}
    )
    assert resp.status_code == 200


def test_wrong_password_still_rejected(db_client):
    _signup(db_client)
    resp = db_client.post("/auth/login", json={"email": VALID["email"], "password": "wrong-one"})
    assert resp.status_code == 401
