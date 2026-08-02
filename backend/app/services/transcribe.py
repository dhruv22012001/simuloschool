"""Video -> transcript, via ffmpeg audio extraction + OpenAI Whisper.

Whisper caps uploads at 25 MB, so the audio is transcoded to mono 16 kHz MP3
(~240 KB/min) and, if it is still too large, split into time segments that are
transcribed separately and concatenated.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from openai import OpenAI

from app.core.config import settings
from app.core.storage import get_s3_client

logger = logging.getLogger(__name__)


class TranscriptionError(RuntimeError):
    pass


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TranscriptionError(f"ffmpeg failed: {result.stderr.strip()[:500]}")


def extract_audio(video_path: Path, out_path: Path) -> Path:
    """Downmix to mono 16 kHz MP3 — the smallest format Whisper handles well."""
    _run_ffmpeg(
        [
            "-i", str(video_path),
            "-vn",  # drop video
            "-ac", "1",
            "-ar", "16000",
            "-b:a", settings.transcode_bitrate,
            str(out_path),
        ]
    )
    return out_path


def split_audio(audio_path: Path, out_dir: Path, segment_seconds: int) -> list[Path]:
    pattern = out_dir / "chunk_%03d.mp3"
    _run_ffmpeg(
        [
            "-i", str(audio_path),
            "-f", "segment",
            "-segment_time", str(segment_seconds),
            "-c", "copy",
            str(pattern),
        ]
    )
    chunks = sorted(out_dir.glob("chunk_*.mp3"))
    if not chunks:
        raise TranscriptionError("audio split produced no chunks")
    return chunks


def _transcribe_file(client: OpenAI, path: Path) -> str:
    with path.open("rb") as fh:
        result = client.audio.transcriptions.create(
            model=settings.whisper_model, file=fh, response_format="text"
        )
    # response_format="text" returns a bare string
    return result if isinstance(result, str) else result.text


def transcribe_storage_key(storage_key: str) -> str:
    """Download the video from object storage and return its transcript."""
    if not settings.openai_api_key:
        raise TranscriptionError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=settings.openai_api_key)
    s3 = get_s3_client()

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        video_path = tmpdir / "source"
        s3.download_file(settings.s3_bucket, storage_key, str(video_path))

        audio_path = extract_audio(video_path, tmpdir / "audio.mp3")
        size = audio_path.stat().st_size

        if size <= settings.whisper_max_upload_bytes:
            parts = [_transcribe_file(client, audio_path)]
        else:
            # Segment so each chunk lands comfortably under the upload cap.
            seconds_per_byte = _audio_duration(audio_path) / max(size, 1)
            segment_seconds = max(
                60, int(settings.whisper_max_upload_bytes * seconds_per_byte * 0.9)
            )
            chunk_dir = tmpdir / "chunks"
            os.makedirs(chunk_dir, exist_ok=True)
            chunks = split_audio(audio_path, chunk_dir, segment_seconds)
            logger.info(
                "transcribing in segments", extra={"ctx": {"segments": len(chunks)}}
            )
            parts = [_transcribe_file(client, chunk) for chunk in chunks]

    transcript = "\n".join(p.strip() for p in parts if p and p.strip())
    if not transcript:
        raise TranscriptionError("transcription returned no text")
    return transcript


def _audio_duration(path: Path) -> float:
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
