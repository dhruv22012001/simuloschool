"""Transcription provider selection and the supplied-transcript shortcut."""

from pathlib import Path

import pytest

from app.core.config import settings
from app.services import transcribe as t

# ------------------------------------------------------- provider choice ----


def test_auto_uses_local_when_no_openai_key(monkeypatch):
    monkeypatch.setattr(settings, "transcription_provider", "auto")
    monkeypatch.setattr(settings, "openai_api_key", None)
    assert t.resolve_provider() == "local"


def test_auto_uses_openai_when_key_present(monkeypatch):
    monkeypatch.setattr(settings, "transcription_provider", "auto")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    assert t.resolve_provider() == "openai"


@pytest.mark.parametrize("provider", ["local", "openai"])
def test_explicit_provider_is_honoured(monkeypatch, provider):
    monkeypatch.setattr(settings, "transcription_provider", provider)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    assert t.resolve_provider() == provider


def test_local_is_used_even_when_a_key_exists(monkeypatch):
    """Setting `local` must not silently fall back to the paid API."""
    monkeypatch.setattr(settings, "transcription_provider", "local")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    assert t.resolve_provider() == "local"


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


def test_dispatches_to_local_provider(monkeypatch, tmp_path):
    _stub_download(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "transcription_provider", "local")
    monkeypatch.setattr(t, "transcribe_local", lambda p: "local text")
    monkeypatch.setattr(t, "transcribe_openai", lambda p: pytest.fail("should not call API"))

    assert t.transcribe_storage_key("videos/x.mp4") == "local text"


def test_dispatches_to_openai_provider(monkeypatch, tmp_path):
    _stub_download(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "transcription_provider", "openai")
    monkeypatch.setattr(t, "transcribe_openai", lambda p: "hosted text")
    monkeypatch.setattr(t, "transcribe_local", lambda p: pytest.fail("should not run locally"))

    assert t.transcribe_storage_key("videos/x.mp4") == "hosted text"


def test_empty_transcription_is_an_error(monkeypatch, tmp_path):
    _stub_download(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "transcription_provider", "local")
    monkeypatch.setattr(t, "transcribe_local", lambda p: "   \n  ")

    with pytest.raises(t.TranscriptionError, match="no text"):
        t.transcribe_storage_key("videos/x.mp4")


def test_blank_lines_are_stripped(monkeypatch, tmp_path):
    _stub_download(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "transcription_provider", "local")
    monkeypatch.setattr(t, "transcribe_local", lambda p: "line one\n\n\n  line two  \n")

    assert t.transcribe_storage_key("videos/x.mp4") == "line one\nline two"
