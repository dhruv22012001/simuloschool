"""App settings (env-driven) and locked product constants."""

from typing import Final

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

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

    @field_validator("database_url", mode="after")
    @classmethod
    def _strip_database_url(cls, v: str) -> str:
        """Trim whitespace around the connection string.

        Connection strings get pasted into hosting dashboards, and a trailing
        space rides along into the last query parameter. Neon's string ends in
        `channel_binding=require`, so the driver sees the value as
        `"require "` and refuses to connect — a failure that reads like a
        network problem rather than a stray character.
        """
        return v.strip()

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in ("production", "prod")

    @property
    def database_host(self) -> str:
        """Host portion of DATABASE_URL, safe to log (no credentials)."""
        try:
            return make_url(self.database_url).host or "(none)"
        except Exception:
            return "(unparseable)"

    def validate_for_production(self) -> list[str]:
        """Config mistakes that make a deploy fail in confusing ways.

        The database default points at localhost, which is right locally and
        useless in production — unset there, the app would otherwise spend its
        startup trying to reach a database that cannot exist, and the platform
        reports it only as an unresponsive service.
        """
        problems: list[str] = []
        if not self.is_production:
            return problems

        host = self.database_host
        if host in ("localhost", "127.0.0.1", "(none)", "(unparseable)"):
            problems.append(
                f"DATABASE_URL points at {host!r} — set it to your managed Postgres "
                "connection string (scheme: postgresql+psycopg://)"
            )
        if self.jwt_secret == "change-me-in-prod":
            problems.append("JWT_SECRET is still the default value")
        if not self.cors_origins_list:
            problems.append("CORS_ALLOWED_ORIGINS is empty — the browser will block every call")
        return problems


settings = Settings()
