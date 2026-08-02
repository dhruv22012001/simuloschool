"""The uploaded -> pending_review pipeline for a single video.

Both entry points share this code:
  - the API schedules generate_for_video() as a background task right after an
    upload, so quizzes build automatically with no operator action;
  - the cron job (app.jobs.generate) sweeps up anything the API missed —
    a process restart mid-generation, or a video an admin re-queued.

Status is the coordination primitive. A video is only ever claimed out of
`uploaded`, under a row lock with SKIP LOCKED, so the background task and a
concurrent job run can never process the same video twice.
"""

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.logging import bind
from app.models.base import VideoStatus
from app.models.question import Question
from app.models.video import Video
from app.services.quiz_generation import generate_quiz
from app.services.transcribe import transcribe_storage_key

logger = logging.getLogger(__name__)


def claim_video(db: Session, video_id: int) -> Video | None:
    """Move one specific video uploaded -> processing, or return None."""
    video = db.scalar(
        select(Video)
        .where(Video.id == video_id, Video.status == VideoStatus.uploaded)
        .with_for_update(skip_locked=True)
    )
    if video is None:
        return None
    video.status = VideoStatus.processing
    db.commit()
    return video


def claim_next_video(db: Session) -> Video | None:
    """Move the oldest queued video uploaded -> processing, or return None."""
    video = db.scalar(
        select(Video)
        .where(Video.status == VideoStatus.uploaded)
        .order_by(Video.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if video is None:
        return None
    video.status = VideoStatus.processing
    db.commit()
    return video


def process_claimed_video(db: Session, video: Video) -> None:
    """Transcribe, generate, and store. The video must already be `processing`."""
    log = bind(logger, video_id=video.id)
    log.info("transcribing video")
    transcript = transcribe_storage_key(video.storage_key)
    video.transcript = transcript
    db.commit()

    log.info("generating questions", extra={"ctx": {"transcript_chars": len(transcript)}})
    quiz = generate_quiz(video.title, transcript)

    # Regeneration is idempotent: a requeued video replaces its question set
    # rather than accumulating a second one. Normal flow deletes nothing.
    removed = db.execute(delete(Question).where(Question.video_id == video.id)).rowcount
    if removed:
        log.info("replacing existing questions", extra={"ctx": {"removed": removed}})

    db.add_all(
        Question(
            video_id=video.id,
            difficulty=q.difficulty,
            text=q.text,
            options=q.options,
            correct_idx=q.correct_idx,
        )
        for q in quiz.questions
    )
    video.status = VideoStatus.pending_review
    db.commit()
    log.info(
        "questions ready for review",
        extra={"ctx": {"question_count": len(quiz.questions)}},
    )


def run_claimed_video(db: Session, video: Video) -> None:
    """Run the pipeline for a claimed video, marking it failed on any error."""
    try:
        process_claimed_video(db, video)
    except Exception:
        db.rollback()
        video.status = VideoStatus.failed
        db.commit()
        bind(logger, video_id=video.id).exception("video processing failed")


def generate_for_video(video_id: int) -> None:
    """Background-task entry point — owns its own session and never raises.

    Scheduled by the upload endpoint. If the video isn't claimable (already
    processing, or the process died and left it mid-flight), this is a no-op
    and the cron job picks it up instead.
    """
    try:
        with SessionLocal() as db:
            video = claim_video(db, video_id)
            if video is None:
                bind(logger, video_id=video_id).info(
                    "video not claimable; leaving it for the cron job"
                )
                return
            run_claimed_video(db, video)
    except Exception:
        # A background task that raises would be swallowed by Starlette; log it.
        bind(logger, video_id=video_id).exception("background generation crashed")
