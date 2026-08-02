"""initial schema: user, video, question, attempt, response

Revision ID: 0001
Revises:
Create Date: 2026-08-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

role_enum = sa.Enum("admin", "student", name="role", native_enum=False, length=20)
video_status_enum = sa.Enum(
    "uploaded",
    "processing",
    "pending_review",
    "published",
    "failed",
    name="videostatus",
    native_enum=False,
    length=20,
)
difficulty_enum = sa.Enum("easy", "medium", "hard", name="difficulty", native_enum=False, length=10)


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", role_enum, nullable=False),
        sa.Column("parent_email", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(op.f("ix_user_email"), "user", ["email"], unique=True)

    op.create_table(
        "video",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("status", video_status_enum, nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(op.f("ix_video_status"), "video", ["status"])

    op.create_table(
        "question",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("video.id"), nullable=False),
        sa.Column("difficulty", difficulty_enum, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("correct_idx", sa.Integer(), nullable=False),
    )
    op.create_index(op.f("ix_question_video_id"), "question", ["video_id"])

    op.create_table(
        "attempt",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("video.id"), nullable=False),
        sa.Column("reached_level", difficulty_enum, nullable=False),
        sa.Column("e_score", sa.Integer(), nullable=True),
        sa.Column("m_score", sa.Integer(), nullable=True),
        sa.Column("h_score", sa.Integer(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_attempt_user_id"), "attempt", ["user_id"])
    op.create_index(op.f("ix_attempt_video_id"), "attempt", ["video_id"])

    op.create_table(
        "response",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("attempt_id", sa.Integer(), sa.ForeignKey("attempt.id"), nullable=False),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("question.id"), nullable=False),
        sa.Column("chosen_idx", sa.Integer(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
    )
    op.create_index(op.f("ix_response_attempt_id"), "response", ["attempt_id"])


def downgrade() -> None:
    op.drop_table("response")
    op.drop_table("attempt")
    op.drop_table("question")
    op.drop_table("video")
    op.drop_table("user")
