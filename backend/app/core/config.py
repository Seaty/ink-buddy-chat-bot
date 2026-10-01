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
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Ink Buddy Chat Bot"
    database_url: str = "postgresql+psycopg://ink_buddy:CHANGE_ME@127.0.0.1:5432/ink_buddy"  # password: docker/.env
    cors_origins: list[str] = ["http://localhost:3000"]

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
    # "mock" until the catalog is embedded into pgvector (POST /api/vision/index)
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
    # Enables POST /api/vision/index. Keep off until core/security.py provides admin auth.
    vision_admin_enabled: bool = False
    # TEMPORARY dev-only auth until JWT exists: every request acts as this user
    # (created on first use). Empty = no auth → protected endpoints return 401.
    dev_auth_email: str | None = None

    @field_validator("catalog_dir", "image_storage_dir")
    @classmethod
    def _relative_to_backend(cls, v: Path) -> Path:
        # "datasets/catalog" in .env must not depend on the working directory
        return v if v.is_absolute() else BACKEND_DIR / v

    @field_validator("image_embed_device", "dev_auth_email", "vision_num_ctx", mode="before")
    @classmethod
    def _empty_device_is_auto(cls, v):
        return v or None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
