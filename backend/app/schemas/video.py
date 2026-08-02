from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.base import Difficulty, VideoStatus


class VideoOut(BaseModel):
    """Student-facing view — never exposes storage keys or transcripts."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: VideoStatus
    created_at: datetime


class VideoAdminOut(VideoOut):
    """Admin view — adds the pipeline fields an admin needs to triage."""

    storage_key: str
    uploaded_by_user_id: int
    has_transcript: bool
    question_count: int


class QuestionAdminOut(BaseModel):
    """Admin review view — includes the answer key (students never see this)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    difficulty: Difficulty
    text: str
    options: list[str]
    correct_idx: int
