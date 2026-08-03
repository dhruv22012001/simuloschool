from app.core import storage
from app.core.request_id import REQUEST_ID_HEADER
from app.routers import health


def test_health_ok(client, monkeypatch):
    monkeypatch.setattr(health, "check_db", lambda: True)
    monkeypatch.setattr(storage, "check_storage", lambda: True)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": True, "storage": True}
    assert resp.headers[REQUEST_ID_HEADER]


def _boom():
    raise RuntimeError("dependency down")


def test_db_down_is_fatal(client, monkeypatch):
    monkeypatch.setattr(health, "check_db", _boom)
    monkeypatch.setattr(storage, "check_storage", lambda: True)
    resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.json() == {"status": "degraded", "db": False, "storage": True}


def test_storage_down_is_degraded_not_fatal(client, monkeypatch):
    """Uploads break, but login/listing/quizzes still serve — a 503 here would
    have the platform kill a mostly-working instance."""
    monkeypatch.setattr(health, "check_db", lambda: True)
    monkeypatch.setattr(storage, "check_storage", _boom)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "degraded", "db": True, "storage": False}


def test_both_down_is_fatal(client, monkeypatch):
    monkeypatch.setattr(health, "check_db", _boom)
    monkeypatch.setattr(storage, "check_storage", _boom)
    resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.json()["status"] == "degraded"


def test_request_id_is_echoed(client, monkeypatch):
    monkeypatch.setattr(health, "check_db", lambda: True)
    monkeypatch.setattr(storage, "check_storage", lambda: True)
    resp = client.get("/health", headers={REQUEST_ID_HEADER: "abc123"})
    assert resp.headers[REQUEST_ID_HEADER] == "abc123"
