from sqlalchemy import JSON, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Difficulty


class Question(Base):
    __tablename__ = "question"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("video.id"), index=True)
    difficulty: Mapped[Difficulty] = mapped_column(Enum(Difficulty, native_enum=False, length=10))
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON)  # generic JSON (portable), NOT Postgres JSONB
    correct_idx: Mapped[int] = mapped_column(Integer)
