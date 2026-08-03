"""App settings (env-driven) and locked product constants."""

from typing import Final

from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# LOCKED PRODUCT RULES — single source of truth, never inline these numbers.
# ---------------------------------------------------------------------------
EASY_QUESTION_COUNT: Final[int] = 10
MEDIUM_QUESTION_COUNT: Final[int] = 5
HARD_QUESTION_COUNT: Final[int] = 5

# Promotion thresholds (no demotion; failing a tier ends the attempt there).
EASY_PASS_THRESHOLD: Final[int] = 5  # pass >= 5 of 10 easy -> medium
MEDIUM_PASS_THRESHOLD: Final[int] = 3  # pass >= 3 of 5 medium -> hard


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"  # local | production

    # Database (Postgres only)
    database_url: str = "postgresql+psycopg://simulo:simulo@localhost:5432/simuloschool"

    # Auth
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 12

    # Admin bootstrap (seeded idempotently at startup when both are set)
    admin_email: str | None = None
    admin_password: str | None = None
    admin_name: str = "Admin"

    # CORS — comma-separated list of allowed origins
    cors_allowed_origins: str = (
        "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000,http://127.0.0.1:3000"
    )

    # Quiz generation (Claude) and transcription (Whisper)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5"
    # Transcription runs on the hosted Whisper API only (`openai`, or `auto`
    # which resolves to it). The in-process faster-whisper path was removed —
    # it pulled ctranslate2/onnxruntime into every deploy build for a code
    # path that never ran once OPENAI_API_KEY was set.
    transcription_provider: str = "openai"
    openai_api_key: str | None = None
    whisper_model: str = "whisper-1"  # hosted API model
    # Whisper rejects uploads over 25 MB; audio is compressed and split below this.
    whisper_max_upload_bytes: int = 24 * 1024 * 1024
    transcode_bitrate: str = "32k"  # mono 16 kHz speech — ~240 KB/min
    generate_batch_size: int = 5  # videos processed per job run

    # Object storage (MinIO locally, Cloudflare R2 in prod — same boto3 client)
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: str = "minioadmin"
    s3_bucket: str = "videos"
    s3_region: str = "auto"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


settings = Settings()
