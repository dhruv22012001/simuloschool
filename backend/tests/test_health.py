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


def test_health_degraded_when_db_down(client, monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(health, "check_db", boom)
    monkeypatch.setattr(storage, "check_storage", lambda: True)
    resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.json()["db"] is False


def test_request_id_is_echoed(client, monkeypatch):
    monkeypatch.setattr(health, "check_db", lambda: True)
    monkeypatch.setattr(storage, "check_storage", lambda: True)
    resp = client.get("/health", headers={REQUEST_ID_HEADER: "abc123"})
    assert resp.headers[REQUEST_ID_HEADER] == "abc123"
