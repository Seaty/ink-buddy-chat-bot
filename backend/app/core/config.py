"""Application settings. Shared across the backend.

Values come from environment variables, then backend/.env (see .env.example
for every key). Defaults below are fallbacks only. This is the single source
of configuration: the ai/ layer takes its values from here via services/.
Settings are cached — restart the app after editing .env.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Ink Buddy Chat Bot"
    database_url: str = "postgresql+psycopg://ink_buddy:CHANGE_ME@127.0.0.1:5432/ink_buddy"  # password: docker/.env
    cors_origins: list[str] = ["http://localhost:3000"]
    app_environment: Literal["development", "production"] = "development"
    auth_jwt_secret: str | None = None
    auth_jwt_issuer: str = "ink-buddy"
    auth_jwt_audience: str = "ink-buddy-api"
    auth_access_seconds: int = 900
    auth_session_seconds: int = 604800
    auth_guest_seconds: int = 86400
    guest_retention_seconds: int = 86400
    auth_limiter_storage_uri: str = "memory://"
    auth_workers: int = 1

    auth_reset_seconds: int = 900
    auth_reset_cooldown_seconds: int = 60
    auth_frontend_url: str = "http://localhost:3000"
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = False
    smtp_ssl: bool = False
    smtp_sender: str = "Ink Buddy <noreply@ink-buddy.local>"
    smtp_timeout_seconds: int = 10

    @property
    def secure_cookies(self) -> bool:
        return self.app_environment == "production"

    def validate_auth(self) -> None:
        if not self.auth_jwt_secret or len(self.auth_jwt_secret.encode()) < 32:
            raise RuntimeError(
                "AUTH_JWT_SECRET must contain at least 32 bytes; no default is supplied"
            )
        if (
            min(
                self.auth_access_seconds,
                self.auth_session_seconds,
                self.auth_guest_seconds,
                self.guest_retention_seconds,
                self.auth_reset_seconds,
                self.auth_reset_cooldown_seconds,
                self.smtp_timeout_seconds,
            )
            <= 0
        ):
            raise RuntimeError("Auth lifetimes must be positive")
        from urllib.parse import urlsplit

        url = urlsplit(self.auth_frontend_url)
        if (
            url.scheme not in ("http", "https")
            or not url.netloc
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in ("", "/")
        ):
            raise RuntimeError("AUTH_FRONTEND_URL must be a trusted frontend origin")
        if self.smtp_starttls and self.smtp_ssl:
            raise RuntimeError("SMTP_STARTTLS and SMTP_SSL are mutually exclusive")
        if self.app_environment == "production" and (
            url.scheme != "https" or not (self.smtp_starttls or self.smtp_ssl)
        ):
            raise RuntimeError("Production password reset requires HTTPS and SMTP TLS")
        if self.auth_workers < 1:
            raise RuntimeError("AUTH_WORKERS must be positive")
        if self.auth_workers > 1 and self.auth_limiter_storage_uri == "memory://":
            raise RuntimeError(
                "Multiple workers require shared AUTH_LIMITER_STORAGE_URI"
            )

    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout_s: float = 300.0

    # --- Vision / Image RAG (docs/architecture/IMAGE_RAG_DESIGN.md §1.7) ---
    vision_model: str = "qwen3-vl:latest"
    vision_num_predict: int = 6144  # room for qwen3-vl's thinking trace
    # Context window for the vision model; None = Ollama default (4096 here). Larger needs more VRAM:
    # qwen3-vl:latest at 16384 grew from 6.2 to 8.1 GB and ran 57% on CPU on a 6 GB GPU.
    vision_num_ctx: int | None = None
    image_embed_model: str = "Qwen/Qwen3-VL-Embedding-2B"
    image_embed_device: str | None = None  # None → cuda if available, else cpu
    image_embed_dim: int = 2048
    image_embed_max_pixels: int = 800 * 800
    # "mock" until the catalog is embedded into pgvector (POST /api/v1/admin/image-index)
    image_retriever: Literal["mock", "pgvector"] = "mock"
    catalog_dir: Path = BACKEND_DIR / "datasets" / "catalog"
    image_top_k: int = 5
    image_tau_similar: float = 0.55
    # No match: offer the nearest products ("did you mean?") scoring at least this, up to this many
    image_tau_suggest: float = 0.47  # random-noise / plain-colour photos scored 0.39-0.46; a partial crop of a real product 0.47-0.53 (3 samples; tune on real photos)
    image_suggest_count: int = 3
    image_w_image: float = 0.6
    image_w_caption: float = 0.4
    image_max_bytes: int = 5 * 1024 * 1024
    image_max_pixels: int = 40_000_000
    # Private storage for user uploads (never served directly); relative → backend/
    image_storage_dir: Path = BACKEND_DIR / "uploads"
    image_message_max_chars: int = 1000
    # Answer find-similar / price questions from retrieval alone, skipping the VLM
    image_fast_path: bool = True
    # Fast path found nothing: true → vision model (crop, is-stationery check; slow), false → "did you mean?" at once
    image_escalate_on_no_match: bool = True
    # Enables indexing in addition to the required admin role guard.
    vision_admin_enabled: bool = False

    @field_validator("catalog_dir", "image_storage_dir")
    @classmethod
    def _relative_to_backend(cls, v: Path) -> Path:
        # "datasets/catalog" in .env must not depend on the working directory
        return v if v.is_absolute() else BACKEND_DIR / v

    @field_validator("image_embed_device", "vision_num_ctx", mode="before")
    @classmethod
    def _empty_device_is_auto(cls, v):
        return v or None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
