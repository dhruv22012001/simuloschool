"""The uploaded -> pending_review pipeline, including the supplied-transcript path."""

import pytest
import sqlalchemy as sa

from app.models.base import Difficulty, VideoStatus
from app.models.question import Question
from app.services import pipeline
from app.services.quiz_generation import GeneratedQuestion, GeneratedQuiz


def _quiz(n_easy=1, n_medium=1, n_hard=1) -> GeneratedQuiz:
    def q(d):
        return GeneratedQuestion(
            difficulty=d, text=f"{d} question?", options=["a", "b", "c", "d"], correct_idx=2
        )

    return GeneratedQuiz(
        questions=[q(Difficulty.easy)] * n_easy
        + [q(Difficulty.medium)] * n_medium
        + [q(Difficulty.hard)] * n_hard
    )


@pytest.fixture()
def stub_generation(monkeypatch):
    """Replace the LLM call; record the transcript it was handed."""
    seen: dict = {}

    def fake_generate(title, transcript):
        seen["title"] = title
        seen["transcript"] = transcript
        return _quiz()

    monkeypatch.setattr(pipeline, "generate_quiz", fake_generate)
    return seen


# ------------------------------------------------------------- claiming ----


def test_claim_moves_uploaded_to_processing(db, make_video):
    video = make_video(VideoStatus.uploaded)
    claimed = pipeline.claim_video(db, video.id)
    assert claimed is not None
    assert claimed.status == VideoStatus.processing


@pytest.mark.parametrize(
    "status",
    [VideoStatus.processing, VideoStatus.pending_review, VideoStatus.published, VideoStatus.failed],
)
def test_claim_ignores_videos_not_queued(db, make_video, status):
    """Only `uploaded` is claimable — this is what stops double-generation."""
    video = make_video(status)
    assert pipeline.claim_video(db, video.id) is None


def test_claim_next_takes_oldest_first(db, make_video):
    first = make_video(VideoStatus.uploaded, title="first")
    make_video(VideoStatus.uploaded, title="second")
    assert pipeline.claim_next_video(db).id == first.id


def test_claim_next_returns_none_when_queue_empty(db, make_video):
    make_video(VideoStatus.published)
    assert pipeline.claim_next_video(db) is None


# ---------------------------------------------- supplied vs auto transcript ----


def test_supplied_transcript_skips_transcription(db, make_video, monkeypatch, stub_generation):
    video = make_video(VideoStatus.processing, transcript="The teacher explains fractions.")
    monkeypatch.setattr(
        pipeline, "transcribe_storage_key", lambda key: pytest.fail("should not transcribe")
    )

    pipeline.process_claimed_video(db, video)

    assert stub_generation["transcript"] == "The teacher explains fractions."
    assert video.status == VideoStatus.pending_review


def test_missing_transcript_triggers_transcription(db, make_video, monkeypatch, stub_generation):
    video = make_video(VideoStatus.processing)
    monkeypatch.setattr(pipeline, "transcribe_storage_key", lambda key: "auto transcript")

    pipeline.process_claimed_video(db, video)

    assert stub_generation["transcript"] == "auto transcript"
    assert video.transcript == "auto transcript"  # persisted for reuse


def test_blank_transcript_is_treated_as_missing(db, make_video, monkeypatch, stub_generation):
    video = make_video(VideoStatus.processing, transcript="   \n  ")
    monkeypatch.setattr(pipeline, "transcribe_storage_key", lambda key: "auto transcript")

    pipeline.process_claimed_video(db, video)
    assert stub_generation["transcript"] == "auto transcript"


# ------------------------------------------------------------- outcomes ----


def test_success_stores_questions_and_awaits_review(db, make_video, monkeypatch, stub_generation):
    video = make_video(VideoStatus.processing, transcript="text")
    pipeline.process_claimed_video(db, video)

    stored = db.scalars(sa.select(Question).where(Question.video_id == video.id)).all()
    assert len(stored) == 3
    assert {q.difficulty for q in stored} == {
        Difficulty.easy,
        Difficulty.medium,
        Difficulty.hard,
    }
    # Never straight to published — an admin must approve.
    assert video.status == VideoStatus.pending_review


def test_regeneration_replaces_questions_rather_than_duplicating(
    db, make_video, make_question, monkeypatch, stub_generation
):
    video = make_video(VideoStatus.processing, transcript="text")
    make_question(video, text="stale question")

    pipeline.process_claimed_video(db, video)

    stored = db.scalars(sa.select(Question).where(Question.video_id == video.id)).all()
    assert len(stored) == 3
    assert "stale question" not in [q.text for q in stored]


def test_failure_marks_video_failed_and_keeps_storage_key(db, make_video, monkeypatch):
    video = make_video(VideoStatus.processing)
    key = video.storage_key
    monkeypatch.setattr(
        pipeline,
        "transcribe_storage_key",
        lambda k: (_ for _ in ()).throw(RuntimeError("whisper exploded")),
    )

    pipeline.run_claimed_video(db, video)

    assert video.status == VideoStatus.failed
    # The video must survive so a retry can reuse it without re-uploading.
    assert video.storage_key == key


def test_failure_leaves_no_partial_questions(db, make_video, monkeypatch):
    video = make_video(VideoStatus.processing, transcript="text")
    monkeypatch.setattr(
        pipeline,
        "generate_quiz",
        lambda title, transcript: (_ for _ in ()).throw(RuntimeError("bad quiz")),
    )

    pipeline.run_claimed_video(db, video)

    assert video.status == VideoStatus.failed
    assert db.scalars(sa.select(Question).where(Question.video_id == video.id)).all() == []
