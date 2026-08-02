import os

# Deterministic test env — set before any app import reads Settings.
os.environ.setdefault("JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://simulo:simulo@localhost:5432/simuloschool")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    # Tests must not require live services; anything touching DB/storage is
    # monkeypatched in the individual tests.
    return TestClient(app)
