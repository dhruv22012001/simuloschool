"""Transcription provider validation and the download -> transcript dispatch."""

from pathlib import Path

import pytest

from app.core.config import settings
from app.services import transcribe as t

# ------------------------------------------------------- provider choice ----


def test_auto_resolves_to_openai(monkeypatch):
    monkeypatch.setattr(settings, "transcription_provider", "auto")
    assert t.resolve_provider() == "openai"


def test_openai_is_honoured(monkeypatch):
    monkeypatch.setattr(settings, "transcription_provider", "openai")
    assert t.resolve_provider() == "openai"


def test_local_is_rejected_with_a_migration_hint(monkeypatch):
    """A stale `local` from before the faster-whisper removal must fail loudly."""
    monkeypatch.setattr(settings, "transcription_provider", "local")
    with pytest.raises(t.TranscriptionError, match="no longer supported"):
        t.resolve_provider()


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "transcription_provider", "magic")
    with pytest.raises(t.TranscriptionError, match="unknown TRANSCRIPTION_PROVIDER"):
        t.resolve_provider()


def test_openai_without_key_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "openai_api_key", None)
    with pytest.raises(t.TranscriptionError, match="OPENAI_API_KEY is not set"):
        t.transcribe_openai(tmp_path / "audio.mp3")


# ------------------------------------------------------------- dispatch ----


def _stub_download(monkeypatch, tmp_path: Path):
    class FakeS3:
        def download_file(self, Bucket, Key, path):  # noqa: N803
            Path(path).write_bytes(b"fake-video")

    monkeypatch.setattr(t, "get_s3_client", lambda: FakeS3())
    monkeypatch.setattr(t, "extract_audio", lambda video, out: out)
    monkeypatch.setattr(settings, "transcription_provider", "openai")


def test_dispatches_to_openai_provider(monkeypatch, tmp_path):
    _stub_download(monkeypatch, tmp_path)
    monkeypatch.setattr(t, "transcribe_openai", lambda p: "hosted text")

    assert t.transcribe_storage_key("videos/x.mp4") == "hosted text"


def test_bad_provider_fails_before_downloading(monkeypatch, tmp_path):
    """Validation happens up front — no S3 pull for a misconfigured job."""
    _stub_download(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "transcription_provider", "local")
    monkeypatch.setattr(t, "get_s3_client", lambda: pytest.fail("should not download"))

    with pytest.raises(t.TranscriptionError, match="no longer supported"):
        t.transcribe_storage_key("videos/x.mp4")


def test_empty_transcription_is_an_error(monkeypatch, tmp_path):
    _stub_download(monkeypatch, tmp_path)
    monkeypatch.setattr(t, "transcribe_openai", lambda p: "   \n  ")

    with pytest.raises(t.TranscriptionError, match="no text"):
        t.transcribe_storage_key("videos/x.mp4")


def test_blank_lines_are_stripped(monkeypatch, tmp_path):
    _stub_download(monkeypatch, tmp_path)
    monkeypatch.setattr(t, "transcribe_openai", lambda p: "line one\n\n\n  line two  \n")

    assert t.transcribe_storage_key("videos/x.mp4") == "line one\nline two"
