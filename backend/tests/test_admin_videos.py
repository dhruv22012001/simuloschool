"""Admin video pipeline: upload, listing, review, publish, retry, delete."""

import io

import pytest

from app.models.base import Difficulty, VideoStatus
from app.models.question import Question
from app.models.video import Video


def _upload(client, headers, title="A lesson", content=b"fake-bytes", ctype="video/mp4"):
    return client.post(
        "/admin/videos",
        headers=headers,
        files={"file": ("lesson.mp4", io.BytesIO(content), ctype)},
        data={"title": title},
    )


@pytest.fixture(autouse=True)
def _no_background_generation(monkeypatch):
    """Upload schedules generation; tests assert storage/DB, not the LLM calls."""
    import app.routers.admin as admin_router

    calls: list[int] = []
    monkeypatch.setattr(admin_router, "generate_for_video", calls.append)
    return calls


# ---------------------------------------------------------------- upload ----


def test_upload_stores_object_and_row(db_client, admin_headers, fake_s3, db):
    resp = _upload(db_client, admin_headers, title="  Fractions  ", content=b"video-data")
    assert resp.status_code == 201
    body = resp.json()

    assert body["status"] == "uploaded"
    assert body["title"] == "Fractions"  # whitespace trimmed
    assert body["question_count"] == 0
    assert body["has_transcript"] is False

    video = db.get(Video, body["id"])
    assert video is not None
    assert fake_s3.objects[video.storage_key] == b"video-data"


def test_upload_generates_unique_key_and_keeps_extension(db_client, admin_headers, fake_s3):
    first = _upload(db_client, admin_headers).json()["storage_key"]
    second = _upload(db_client, admin_headers).json()["storage_key"]

    assert first != second
    assert first.startswith("videos/") and first.endswith(".mp4")
    # The client-supplied filename must not survive into the key.
    assert "lesson" not in first


def test_upload_rejects_non_video(db_client, admin_headers, fake_s3):
    resp = _upload(db_client, admin_headers, ctype="text/plain")
    assert resp.status_code == 415
    assert fake_s3.objects == {}


def test_upload_schedules_generation(db_client, admin_headers, fake_s3, _no_background_generation):
    video_id = _upload(db_client, admin_headers).json()["id"]
    assert _no_background_generation == [video_id]


def test_upload_reports_storage_failure_without_creating_row(
    db_client, admin_headers, monkeypatch, db
):
    import app.routers.admin as admin_router

    from .conftest import FakeS3

    monkeypatch.setattr(admin_router, "get_s3_client", lambda: FakeS3(fail_on={"upload"}))
    before = len(list(db.scalars(__import__("sqlalchemy").select(Video))))

    resp = _upload(db_client, admin_headers)
    assert resp.status_code == 502
    assert len(list(db.scalars(__import__("sqlalchemy").select(Video)))) == before


# ------------------------------------------------------------------ list ----


def test_list_returns_every_status_newest_first(db_client, admin_headers, make_video):
    make_video(VideoStatus.published, title="old")
    make_video(VideoStatus.failed, title="new")

    body = db_client.get("/admin/videos", headers=admin_headers).json()
    assert [v["title"] for v in body] == ["new", "old"]
    assert {v["status"] for v in body} == {"published", "failed"}


def test_list_counts_questions_per_video(db_client, admin_headers, make_video, make_question):
    with_questions = make_video(VideoStatus.pending_review)
    without = make_video(VideoStatus.uploaded)
    for _ in range(3):
        make_question(with_questions)

    by_id = {v["id"]: v for v in db_client.get("/admin/videos", headers=admin_headers).json()}
    assert by_id[with_questions.id]["question_count"] == 3
    assert by_id[without.id]["question_count"] == 0


def test_has_transcript_reflects_stored_transcript(
    db_client, admin_headers, make_video, db
):
    video = make_video(VideoStatus.pending_review)
    video.transcript = "some words"
    db.commit()

    body = db_client.get("/admin/videos", headers=admin_headers).json()
    assert body[0]["has_transcript"] is True


# --------------------------------------------------------------- review ----


def test_questions_include_answer_key(db_client, admin_headers, make_video, make_question):
    video = make_video(VideoStatus.pending_review)
    make_question(video, Difficulty.hard, text="Why?", options=["a", "b"], correct_idx=1)

    body = db_client.get(f"/admin/videos/{video.id}/questions", headers=admin_headers).json()
    assert body[0]["difficulty"] == "hard"
    assert body[0]["options"] == ["a", "b"]
    assert body[0]["correct_idx"] == 1


def test_questions_404_for_unknown_video(db_client, admin_headers):
    assert db_client.get("/admin/videos/9999/questions", headers=admin_headers).status_code == 404


# -------------------------------------------------------------- publish ----


def test_publish_moves_pending_review_to_published(
    db_client, admin_headers, make_video, make_question, db
):
    video = make_video(VideoStatus.pending_review)
    make_question(video)

    resp = db_client.post(f"/admin/videos/{video.id}/publish", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"
    db.refresh(video)
    assert video.status == VideoStatus.published


@pytest.mark.parametrize(
    "status", [VideoStatus.uploaded, VideoStatus.processing, VideoStatus.failed]
)
def test_publish_rejects_wrong_status(db_client, admin_headers, make_video, status):
    video = make_video(status)
    resp = db_client.post(f"/admin/videos/{video.id}/publish", headers=admin_headers)
    assert resp.status_code == 409
    assert status.value in resp.json()["detail"]


def test_publish_rejects_video_with_no_questions(db_client, admin_headers, make_video):
    video = make_video(VideoStatus.pending_review)
    resp = db_client.post(f"/admin/videos/{video.id}/publish", headers=admin_headers)
    assert resp.status_code == 409
    assert "no questions" in resp.json()["detail"]


def test_publish_404_for_unknown_video(db_client, admin_headers):
    assert db_client.post("/admin/videos/9999/publish", headers=admin_headers).status_code == 404


# ---------------------------------------------------------------- retry ----


@pytest.mark.parametrize("status", [VideoStatus.failed, VideoStatus.pending_review])
def test_retry_requeues_without_touching_storage(
    db_client, admin_headers, make_video, status, db, _no_background_generation
):
    video = make_video(status)
    original_key = video.storage_key

    resp = db_client.post(f"/admin/videos/{video.id}/retry", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "uploaded"
    # The whole point: the same stored file is reused, no re-upload.
    assert resp.json()["storage_key"] == original_key
    db.refresh(video)
    assert video.storage_key == original_key
    assert _no_background_generation == [video.id]


@pytest.mark.parametrize("status", [VideoStatus.uploaded, VideoStatus.processing])
def test_retry_rejects_in_flight_video(db_client, admin_headers, make_video, status):
    video = make_video(status)
    assert (
        db_client.post(f"/admin/videos/{video.id}/retry", headers=admin_headers).status_code
        == 409
    )


# --------------------------------------------------------------- delete ----


def test_delete_removes_object_row_and_questions(
    db_client, admin_headers, make_video, make_question, fake_s3, db
):
    video = make_video(VideoStatus.published)
    make_question(video)
    fake_s3.objects[video.storage_key] = b"data"
    video_id, key = video.id, video.storage_key

    resp = db_client.delete(f"/admin/videos/{video_id}", headers=admin_headers)
    assert resp.status_code == 204

    assert key not in fake_s3.objects
    assert db.get(Video, video_id) is None
    import sqlalchemy as sa

    remaining = db.scalars(sa.select(Question).where(Question.video_id == video_id)).all()
    assert remaining == []


def test_delete_404_for_unknown_video(db_client, admin_headers, fake_s3):
    assert db_client.delete("/admin/videos/9999", headers=admin_headers).status_code == 404


def test_delete_keeps_everything_when_storage_fails(
    db_client, admin_headers, make_video, monkeypatch, db
):
    import app.routers.admin as admin_router

    from .conftest import FakeS3

    video = make_video(VideoStatus.failed)
    monkeypatch.setattr(admin_router, "get_s3_client", lambda: FakeS3(fail_on={"delete"}))

    resp = db_client.delete(f"/admin/videos/{video.id}", headers=admin_headers)
    assert resp.status_code == 502
    # Nothing half-deleted: the row must survive so the delete can be retried.
    assert db.get(Video, video.id) is not None


def test_delete_only_touches_the_target_video(
    db_client, admin_headers, make_video, make_question, fake_s3, db
):
    doomed = make_video(VideoStatus.failed)
    keeper = make_video(VideoStatus.published)
    make_question(keeper)

    db_client.delete(f"/admin/videos/{doomed.id}", headers=admin_headers)

    import sqlalchemy as sa

    assert db.get(Video, keeper.id) is not None
    assert db.scalars(sa.select(Question).where(Question.video_id == keeper.id)).all() != []


# ----------------------------------------------------------- transcript ----


def test_upload_accepts_optional_transcript(db_client, admin_headers, fake_s3, db):
    resp = db_client.post(
        "/admin/videos",
        headers=admin_headers,
        files={"file": ("lesson.mp4", io.BytesIO(b"v"), "video/mp4")},
        data={"title": "With transcript", "transcript": "  The lesson text.  "},
    )
    assert resp.status_code == 201
    assert resp.json()["has_transcript"] is True
    assert db.get(Video, resp.json()["id"]).transcript == "The lesson text."


def test_upload_without_transcript_leaves_it_empty(db_client, admin_headers, fake_s3, db):
    resp = _upload(db_client, admin_headers)
    assert resp.json()["has_transcript"] is False
    assert db.get(Video, resp.json()["id"]).transcript is None


def test_blank_transcript_field_is_ignored(db_client, admin_headers, fake_s3, db):
    resp = db_client.post(
        "/admin/videos",
        headers=admin_headers,
        files={"file": ("lesson.mp4", io.BytesIO(b"v"), "video/mp4")},
        data={"title": "Blank", "transcript": "   "},
    )
    assert resp.json()["has_transcript"] is False


def test_put_transcript_stores_and_requeues(
    db_client, admin_headers, make_video, db, _no_background_generation
):
    video = make_video(VideoStatus.failed)
    resp = db_client.put(
        f"/admin/videos/{video.id}/transcript",
        headers=admin_headers,
        json={"transcript": "  Pasted transcript.  "},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "uploaded"
    assert resp.json()["has_transcript"] is True
    db.refresh(video)
    assert video.transcript == "Pasted transcript."
    assert _no_background_generation == [video.id]


def test_put_transcript_rejects_empty_body(db_client, admin_headers, make_video):
    video = make_video(VideoStatus.failed)
    resp = db_client.put(
        f"/admin/videos/{video.id}/transcript",
        headers=admin_headers,
        json={"transcript": ""},
    )
    assert resp.status_code == 422


def test_put_transcript_rejects_video_being_processed(db_client, admin_headers, make_video):
    video = make_video(VideoStatus.processing)
    resp = db_client.put(
        f"/admin/videos/{video.id}/transcript",
        headers=admin_headers,
        json={"transcript": "text"},
    )
    assert resp.status_code == 409


def test_put_transcript_404_for_unknown_video(db_client, admin_headers):
    resp = db_client.put(
        "/admin/videos/9999/transcript", headers=admin_headers, json={"transcript": "t"}
    )
    assert resp.status_code == 404
