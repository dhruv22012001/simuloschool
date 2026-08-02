from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, VideoStatus


class Video(Base):
    __tablename__ = "video"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    storage_key: Mapped[str] = mapped_column(String(1024))
    transcript: Mapped[str | None] = mapped_column(Text)  # filled by processing later
    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus, native_enum=False, length=20),
        default=VideoStatus.uploaded,
        index=True,  # generation job and listings both filter on status
    )
    uploaded_by_user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
