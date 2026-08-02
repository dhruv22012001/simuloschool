"""Admin routes must reject students and anonymous callers.

The happy paths need a live database and object storage, so they're exercised
against the running stack rather than here.
"""

import pytest

from app.core.auth import hash_password, require_user
from app.main import app
from app.models.base import Role
from app.models.user import User

ADMIN_ROUTES = [
    ("get", "/admin/videos"),
    ("get", "/admin/videos/1/questions"),
    ("post", "/admin/videos/1/publish"),
    ("post", "/admin/videos/1/retry"),
    ("post", "/admin/videos"),
]


def test_admin_routes_reject_anonymous(client):
    for method, path in ADMIN_ROUTES:
        assert getattr(client, method)(path).status_code == 401, path


@pytest.fixture()
def student_client(client):
    """Client authenticated as a student, with the DB lookup stubbed out."""
    student = User(
        id=7,
        name="Student",
        email="s@example.com",
        password_hash=hash_password("pw"),
        role=Role.student,
    )
    app.dependency_overrides[require_user] = lambda: student
    yield client
    app.dependency_overrides.clear()


def test_admin_routes_reject_students(student_client):
    for method, path in ADMIN_ROUTES:
        resp = getattr(student_client, method)(path)
        assert resp.status_code == 403, f"{path} -> {resp.status_code}"
