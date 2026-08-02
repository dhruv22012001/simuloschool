from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Difficulty


class Attempt(Base):
    __tablename__ = "attempt"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("video.id"), index=True)
    # Level is per-video; every attempt starts at easy. No demotion.
    reached_level: Mapped[Difficulty] = mapped_column(
        Enum(Difficulty, native_enum=False, length=10), default=Difficulty.easy
    )
    e_score: Mapped[int | None] = mapped_column(Integer)  # null until the tier is taken
    m_score: Mapped[int | None] = mapped_column(Integer)  # null if never promoted to medium
    h_score: Mapped[int | None] = mapped_column(Integer)  # null if never promoted to hard
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # null = in progress
