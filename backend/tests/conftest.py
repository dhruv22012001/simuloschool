"""Shared test fixtures.

Tests that only exercise pure logic run anywhere. Route and pipeline tests need
Postgres (the app is Postgres-only by design), so they use a dedicated
`simuloschool_test` database and are skipped with a clear message when no
database is reachable — `uv run pytest` still works with the stack down.

Each database test runs inside a transaction that is rolled back afterwards, so
tests never see each other's rows and the suite is order-independent.
"""

import os

# Deterministic env — must be set before anything imports Settings.
os.environ.setdefault("JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef")
os.environ.setdefault("ADMIN_EMAIL", "")
os.environ.setdefault("ADMIN_PASSWORD", "")

# Port 55432 is the compose stack's second mapping — a natively-installed
# Postgres commonly owns 5432 and would shadow the container. Override with
# TEST_DATABASE_URL if your setup differs.
MAINTENANCE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://simulo:simulo@localhost:55432/simuloschool"
)
TEST_DB = "simuloschool_test"
os.environ["DATABASE_URL"] = MAINTENANCE_URL.rsplit("/", 1)[0] + "/" + TEST_DB

import pytest  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.auth import create_access_token, hash_password, require_user  # noqa: E402
from app.core.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.base import Difficulty, Role, VideoStatus  # noqa: E402
from app.models.question import Question  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.video import Video  # noqa: E402

SKIP_REASON = "Postgres not reachable — start it with `docker compose up -d db`"


def _ensure_test_database() -> str | None:
    """Create the test database if needed. Returns None when Postgres is down."""
    try:
        admin_engine = sa.create_engine(MAINTENANCE_URL, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            exists = conn.execute(
                sa.text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB}
            ).scalar()
            if not exists:
                conn.execute(sa.text(f'CREATE DATABASE "{TEST_DB}"'))
        admin_engine.dispose()
    except Exception:
        return None
    return os.environ["DATABASE_URL"]


@pytest.fixture(scope="session")
def engine():
    url = _ensure_test_database()
    if url is None:
        pytest.skip(SKIP_REASON, allow_module_level=True)
    eng = sa.create_engine(url)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    """A session whose writes are rolled back when the test ends.

    join_transaction_mode="create_savepoint" lets application code call
    commit() normally while the outer transaction still undoes everything.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client():
    """Client with no database — for auth/validation paths that never query."""
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def db_client(db):
    """Client wired to the rolled-back test session."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# Factories
# --------------------------------------------------------------------------


@pytest.fixture()
def make_user(db):
    def _make(role: Role = Role.student, email: str | None = None, **kwargs) -> User:
        user = User(
            name=kwargs.pop("name", role.value.title()),
            email=email or f"{role.value}-{id(object())}@example.com",
            password_hash=hash_password(kwargs.pop("password", "pw12345678")),
            role=role,
            **kwargs,
        )
        db.add(user)
        db.commit()
        return user

    return _make


@pytest.fixture()
def admin(make_user) -> User:
    return make_user(Role.admin, email="admin@example.com", name="Admin")


@pytest.fixture()
def student(make_user) -> User:
    return make_user(Role.student, email="student@example.com", name="Student")


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user)}"}


@pytest.fixture()
def admin_headers(admin) -> dict[str, str]:
    return auth_headers(admin)


@pytest.fixture()
def student_headers(student) -> dict[str, str]:
    return auth_headers(student)


@pytest.fixture()
def make_video(db, admin):
    def _make(status: VideoStatus = VideoStatus.uploaded, **kwargs) -> Video:
        video = Video(
            title=kwargs.pop("title", "A lesson"),
            storage_key=kwargs.pop("storage_key", f"videos/{id(object())}.mp4"),
            status=status,
            uploaded_by_user_id=kwargs.pop("uploaded_by_user_id", admin.id),
            **kwargs,
        )
        db.add(video)
        db.commit()
        return video

    return _make


@pytest.fixture()
def make_question(db):
    def _make(video: Video, difficulty: Difficulty = Difficulty.easy, **kwargs) -> Question:
        question = Question(
            video_id=video.id,
            difficulty=difficulty,
            text=kwargs.pop("text", "What is 2 + 2?"),
            options=kwargs.pop("options", ["3", "4", "5", "6"]),
            correct_idx=kwargs.pop("correct_idx", 1),
        )
        db.add(question)
        db.commit()
        return question

    return _make


@pytest.fixture()
def as_student():
    """Authenticate as a student without touching the database."""
    user = User(
        id=999,
        name="Student",
        email="s@example.com",
        password_hash=hash_password("pw"),
        role=Role.student,
    )
    app.dependency_overrides[require_user] = lambda: user
    yield user
    app.dependency_overrides.pop(require_user, None)


class FakeS3:
    """In-memory stand-in for the S3 client used by the admin router."""

    def __init__(self, fail_on: set[str] | None = None):
        self.objects: dict[str, bytes] = {}
        self.fail_on = fail_on or set()

    def upload_fileobj(self, fileobj, Bucket, Key, ExtraArgs=None):  # noqa: N803
        if "upload" in self.fail_on:
            raise RuntimeError("storage unavailable")
        self.objects[Key] = fileobj.read()

    def delete_object(self, Bucket, Key):  # noqa: N803
        if "delete" in self.fail_on:
            raise RuntimeError("storage unavailable")
        self.objects.pop(Key, None)

    def head_bucket(self, Bucket):  # noqa: N803
        return {}


@pytest.fixture()
def fake_s3(monkeypatch) -> FakeS3:
    import app.routers.admin as admin_router

    fake = FakeS3()
    monkeypatch.setattr(admin_router, "get_s3_client", lambda: fake)
    return fake
