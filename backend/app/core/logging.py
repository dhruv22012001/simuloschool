"""Structured JSON logging to stdout.

Rules:
- Every line is one JSON object with ts/level/logger/message/request_id.
- Use `bind(logger, video_id=..., attempt_id=..., user_id=...)` to attach
  domain context; bound fields appear as top-level keys on every line.
- NEVER log PII (emails, names, passwords) in message bodies or bound fields.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.request_id import get_request_id

_CTX_KEY = "ctx"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id
        ctx = getattr(record, _CTX_KEY, None)
        if ctx:
            payload.update(ctx)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _BoundLogger(logging.LoggerAdapter):
    """LoggerAdapter that merges bound context into every record."""

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        extra = kwargs.get("extra") or {}
        merged = {**self.extra, **extra.get(_CTX_KEY, {})}
        kwargs["extra"] = {_CTX_KEY: merged}
        return msg, kwargs


def bind(logger: logging.Logger | logging.LoggerAdapter, **ctx: Any) -> logging.LoggerAdapter:
    """Return a logger with ctx (e.g. video_id, attempt_id, user_id) attached
    to every subsequent log line. Do not bind PII."""
    if isinstance(logger, logging.LoggerAdapter):
        ctx = {**logger.extra, **ctx}
        logger = logger.logger
    return _BoundLogger(logger, ctx)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Route uvicorn loggers through the root JSON handler.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
