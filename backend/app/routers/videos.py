from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import require_user
from app.core.db import get_db
from app.models.base import VideoStatus
from app.models.user import User
from app.models.video import Video
from app.schemas.video import VideoOut

router = APIRouter(prefix="/videos", tags=["videos"])


@router.get("", response_model=list[VideoOut])
def list_videos(
    _user: User = Depends(require_user), db: Session = Depends(get_db)
) -> list[Video]:
    """Published videos are visible to every logged-in user."""
    return list(
        db.scalars(
            select(Video)
            .where(Video.status == VideoStatus.published)
            .order_by(Video.created_at.desc(), Video.id.desc())
        )
    )
