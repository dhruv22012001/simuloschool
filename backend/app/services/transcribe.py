"""Video -> transcript.

Two providers, chosen by TRANSCRIPTION_PROVIDER:

  local  — faster-whisper running in-process. No API key, no per-minute cost,
           no upload size limit. Needs ~1.2 GB RAM for the `small` model.
  openai — the hosted Whisper API. Fast and light on memory, but costs
           ~$0.006/min and caps uploads at 25 MB, so audio is split first.
  auto   — openai when a key is present, otherwise local.

Either way the video is downloaded once and ffmpeg reduces it to mono 16 kHz
audio before transcription; that is what both providers want.
"""

import logging
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.core.storage import get_s3_client

logger = logging.getLogger(__name__)


class TranscriptionError(RuntimeError):
    pass


# ---------------------------------------------------------------- ffmpeg ----


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TranscriptionError(f"ffmpeg failed: {result.stderr.strip()[:500]}")


def extract_audio(video_path: Path, out_path: Path) -> Path:
    """Downmix to mono 16 kHz MP3 — small, and what Whisper expects."""
    _run_ffmpeg(
        [
            "-i", str(video_path),
            "-vn",  # drop the video stream
            "-ac", "1",
            "-ar", "16000",
            "-b:a", settings.transcode_bitrate,
            str(out_path),
        ]
    )
    return out_path


def audio_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TranscriptionError(f"ffprobe failed: {result.stderr.strip()[:500]}")
    return float(result.stdout.strip())


def split_audio(audio_path: Path, out_dir: Path, segment_seconds: int) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        [
            "-i", str(audio_path),
            "-f", "segment",
            "-segment_time", str(segment_seconds),
            "-c", "copy",
            str(out_dir / "chunk_%03d.mp3"),
        ]
    )
    chunks = sorted(out_dir.glob("chunk_*.mp3"))
    if not chunks:
        raise TranscriptionError("audio split produced no chunks")
    return chunks


# -------------------------------------------------------------- providers ----


def resolve_provider() -> str:
    """Which provider a transcription would use right now."""
    provider = settings.transcription_provider.lower()
    if provider == "auto":
        return "openai" if settings.openai_api_key else "local"
    if provider not in ("openai", "local"):
        raise TranscriptionError(f"unknown TRANSCRIPTION_PROVIDER: {provider}")
    return provider


@lru_cache(maxsize=1)
def _local_model():
    """Load the local model once per process — loading costs seconds."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as err:  # pragma: no cover - dependency is declared
        raise TranscriptionError(
            "faster-whisper is not installed; set TRANSCRIPTION_PROVIDER=openai"
        ) from err
    logger.info(
        "loading local whisper model",
        extra={"ctx": {"model": settings.local_whisper_model}},
    )
    return WhisperModel(
        settings.local_whisper_model,
        device="cpu",
        compute_type=settings.local_whisper_compute_type,
    )


def transcribe_local(audio_path: Path) -> str:
    """Run Whisper in-process. No size limit — it streams the whole file."""
    segments, _info = _local_model().transcribe(str(audio_path), vad_filter=True)
    return " ".join(segment.text.strip() for segment in segments).strip()


def transcribe_openai(audio_path: Path) -> str:
    """Hosted Whisper. Splits audio that exceeds the API's upload cap."""
    if not settings.openai_api_key:
        raise TranscriptionError("OPENAI_API_KEY is not set")
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)

    def _one(path: Path) -> str:
        with path.open("rb") as fh:
            result = client.audio.transcriptions.create(
                model=settings.whisper_model, file=fh, response_format="text"
            )
        return result if isinstance(result, str) else result.text

    size = audio_path.stat().st_size
    if size <= settings.whisper_max_upload_bytes:
        return _one(audio_path)

    seconds_per_byte = audio_duration(audio_path) / max(size, 1)
    segment_seconds = max(60, int(settings.whisper_max_upload_bytes * seconds_per_byte * 0.9))
    chunks = split_audio(audio_path, audio_path.parent / "chunks", segment_seconds)
    logger.info("transcribing in segments", extra={"ctx": {"segments": len(chunks)}})
    return "\n".join(_one(chunk) for chunk in chunks)


# ------------------------------------------------------------------ entry ----


def transcribe_storage_key(storage_key: str) -> str:
    """Download the stored video and return its transcript."""
    provider = resolve_provider()
    logger.info("transcribing", extra={"ctx": {"provider": provider}})

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        video_path = tmpdir / "source"
        get_s3_client().download_file(settings.s3_bucket, storage_key, str(video_path))
        audio_path = extract_audio(video_path, tmpdir / "audio.mp3")

        if provider == "local":
            text = transcribe_local(audio_path)
        else:
            text = transcribe_openai(audio_path)

    transcript = "\n".join(part.strip() for part in text.splitlines() if part.strip())
    if not transcript.strip():
        raise TranscriptionError("transcription returned no text")
    return transcript
