import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core import storage
from app.core.db import engine

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


def check_db() -> bool:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True


@router.get("/health")
def health(response: Response) -> dict:
    checks = {"db": False, "storage": False}
    for name, check in (("db", check_db), ("storage", storage.check_storage)):
        try:
            checks[name] = bool(check())
        except Exception:
            logger.exception("health check failed", extra={"ctx": {"check": name}})
    ok = all(checks.values())
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if ok else "degraded", **checks}
