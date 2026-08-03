"""Admin-only endpoints: upload a video, review generated questions, publish.

Every route depends on require_admin — students can never reach these.
"""

import logging
import uuid
from pathlib import PurePosixPath

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import require_admin
from app.core.config import settings
from app.core.db import get_db
from app.core.logging import bind
from app.core.storage import get_s3_client
from app.models.attempt import Attempt
from app.models.base import VideoStatus
from app.models.question import Question
from app.models.response import Response
from app.models.user import User
from app.models.video import Video
from app.schemas.video import QuestionAdminOut, TranscriptIn, VideoAdminOut
from app.services.pipeline import generate_for_video

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)

ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm", "video/x-matroska"}


def _to_admin_out(video: Video, question_count: int) -> VideoAdminOut:
    return VideoAdminOut(
        id=video.id,
        title=video.title,
        status=video.status,
        created_at=video.created_at,
        storage_key=video.storage_key,
        uploaded_by_user_id=video.uploaded_by_user_id,
        has_transcript=bool(video.transcript),
        question_count=question_count,
    )


def _question_counts(db: Session, video_ids: list[int]) -> dict[int, int]:
    if not video_ids:
        return {}
    rows = db.execute(
        select(Question.video_id, func.count(Question.id))
        .where(Question.video_id.in_(video_ids))
        .group_by(Question.video_id)
    ).all()
    return {video_id: count for video_id, count in rows}


@router.post("/videos", response_model=VideoAdminOut, status_code=status.HTTP_201_CREATED)
def upload_video(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    file: UploadFile = File(...),
    transcript: str | None = Form(None),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> VideoAdminOut:
    """Store the video and immediately start generating its quiz.

    `transcript` is optional. Supply it and transcription is skipped entirely;
    leave it out and the pipeline transcribes the audio itself.
    """
    if file.content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported video type: {file.content_type}",
        )

    # Model-supplied filenames are untrusted — keep only the extension.
    suffix = PurePosixPath(file.filename or "").suffix[:10]
    storage_key = f"videos/{uuid.uuid4().hex}{suffix}"

    s3 = get_s3_client()
    try:
        s3.upload_fileobj(
            file.file,
            settings.s3_bucket,
            storage_key,
            ExtraArgs={"ContentType": file.content_type},
        )
    except Exception:
        logger.exception("video upload to storage failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not store the video"
        ) from None

    video = Video(
        title=title.strip(),
        storage_key=storage_key,
        transcript=transcript.strip() if transcript and transcript.strip() else None,
        status=VideoStatus.uploaded,
        uploaded_by_user_id=admin.id,
    )
    db.add(video)
    db.commit()
    bind(logger, video_id=video.id, user_id=admin.id).info("video uploaded")

    # Generation starts as soon as this response is sent — no operator step.
    # The cron job is the backstop if this process dies mid-generation.
    background_tasks.add_task(generate_for_video, video.id)
    return _to_admin_out(video, question_count=0)


@router.get("/videos", response_model=list[VideoAdminOut])
def list_all_videos(
    _admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[VideoAdminOut]:
    """Every video in every state — the admin's pipeline view."""
    # id breaks ties: created_at comes from now(), which is constant within a
    # transaction, so timestamps alone don't give a stable order.
    videos = list(db.scalars(select(Video).order_by(Video.created_at.desc(), Video.id.desc())))
    counts = _question_counts(db, [v.id for v in videos])
    return [_to_admin_out(v, counts.get(v.id, 0)) for v in videos]


def _get_video(db: Session, video_id: int) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    return video


@router.get("/videos/{video_id}/questions", response_model=list[QuestionAdminOut])
def list_questions(
    video_id: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[Question]:
    """Generated questions with the answer key, for review before publishing."""
    _get_video(db, video_id)
    return list(
        db.scalars(
            select(Question).where(Question.video_id == video_id).order_by(Question.id)
        )
    )


@router.post("/videos/{video_id}/publish", response_model=VideoAdminOut)
def publish_video(
    video_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> VideoAdminOut:
    """pending_review -> published. Published videos are visible to all students."""
    video = _get_video(db, video_id)
    if video.status != VideoStatus.pending_review:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only videos in pending_review can be published "
                f"(this one is {video.status.value})"
            ),
        )
    count = _question_counts(db, [video.id]).get(video.id, 0)
    if count == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Video has no questions to publish"
        )
    video.status = VideoStatus.published
    db.commit()
    bind(logger, video_id=video.id, user_id=admin.id).info("video published")
    return _to_admin_out(video, count)


@router.post("/videos/{video_id}/retry", response_model=VideoAdminOut)
def retry_video(
    video_id: int,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> VideoAdminOut:
    """Re-run generation against the already-stored video — no re-upload.

    The video file stays in object storage untouched; only the transcript and
    question set are rebuilt.
    """
    video = _get_video(db, video_id)
    if video.status not in (VideoStatus.failed, VideoStatus.pending_review):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only failed or pending-review videos can be regenerated "
                f"(this one is {video.status.value})"
            ),
        )
    video.status = VideoStatus.uploaded
    db.commit()
    bind(logger, video_id=video.id, user_id=admin.id).info(
        "regenerating from stored video", extra={"ctx": {"reused_storage_key": True}}
    )
    background_tasks.add_task(generate_for_video, video.id)
    return _to_admin_out(video, question_count=0)


@router.put("/videos/{video_id}/transcript", response_model=VideoAdminOut)
def set_transcript(
    video_id: int,
    body: TranscriptIn,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> VideoAdminOut:
    """Attach a transcript to an existing video and regenerate from it.

    Use this when auto-transcription failed or produced poor text: supplying
    the transcript here skips speech-to-text on the next run.
    """
    video = _get_video(db, video_id)
    if video.status == VideoStatus.processing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This video is currently being processed — wait for it to finish",
        )

    video.transcript = body.transcript.strip()
    video.status = VideoStatus.uploaded
    db.commit()
    bind(logger, video_id=video.id, user_id=admin.id).info("transcript supplied by admin")
    background_tasks.add_task(generate_for_video, video.id)
    return _to_admin_out(video, _question_counts(db, [video.id]).get(video.id, 0))


@router.delete("/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> None:
    """Delete the lesson everywhere: the stored video, its quiz, and any attempts.

    The object is removed first because S3 deletes are idempotent — if the
    database step then fails, retrying the whole delete still succeeds. Doing it
    the other way round could strand an unreachable object with no row naming it.
    """
    video = _get_video(db, video_id)
    log = bind(logger, video_id=video.id, user_id=admin.id)

    try:
        get_s3_client().delete_object(Bucket=settings.s3_bucket, Key=video.storage_key)
    except Exception:
        log.exception("could not delete video from storage")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not delete the video from storage — nothing was removed",
        ) from None

    # Child rows first: response -> attempt -> question -> video.
    attempt_ids = select(Attempt.id).where(Attempt.video_id == video_id)
    db.execute(sql_delete(Response).where(Response.attempt_id.in_(attempt_ids)))
    db.execute(sql_delete(Attempt).where(Attempt.video_id == video_id))
    db.execute(sql_delete(Question).where(Question.video_id == video_id))
    db.delete(video)
    db.commit()
    log.info("lesson deleted")
