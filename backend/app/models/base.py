from enum import StrEnum

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Role(StrEnum):
    admin = "admin"
    student = "student"


class VideoStatus(StrEnum):
    uploaded = "uploaded"
    processing = "processing"
    pending_review = "pending_review"
    published = "published"
    failed = "failed"


class Difficulty(StrEnum):
    easy = "easy"
    medium = "medium"
    hard = "hard"
