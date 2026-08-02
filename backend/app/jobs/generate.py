"""Quiz-generation sweep — a safety net, not the primary path.

Generation normally starts automatically the moment an admin uploads a video
(the API schedules it as a background task). This job exists to catch anything
that path missed: a process restart mid-generation, or a video an admin
re-queued after a failure.

Run with `python -m app.jobs.generate`. Locally by hand; in prod a GitHub
Actions cron runs the same entrypoint. Exits when the queue is empty.
"""

import logging
import sys

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging
from app.services.pipeline import claim_next_video, run_claimed_video

logger = logging.getLogger(__name__)


def run() -> int:
    """Process up to generate_batch_size videos. Returns the number processed."""
    processed = 0
    while processed < settings.generate_batch_size:
        with SessionLocal() as db:
            video = claim_next_video(db)
            if video is None:
                break
            run_claimed_video(db, video)
            processed += 1
    return processed


def main() -> int:
    configure_logging()
    logger.info("generate job started")
    try:
        processed = run()
    except Exception:
        logger.exception("generate job crashed")
        return 1
    if processed == 0:
        logger.info("no pending videos")
    logger.info("generate job finished", extra={"ctx": {"processed": processed}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
