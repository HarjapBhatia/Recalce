"""
app/core/config.py
------------------
Centralised settings loaded from .env via pydantic-settings.

All environment variables are read once here and referenced throughout
the codebase as `from app.core.config import settings`.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
REPOSITORY_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    # Prefer backend/.env when present, while retaining compatibility with the
    # existing repository-level .env file.
    model_config = SettingsConfigDict(
        env_file=(REPOSITORY_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-me-in-production"
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://localhost/reconflow"

    # ── Redis / Celery ────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ── Backblaze B2 ─────────────────────────────────────────────────────────
    B2_APPLICATION_KEY_ID: str = ""
    B2_APPLICATION_KEY: str = ""
    B2_BUCKET_NAME: str = "reconflow-uploads"
    B2_ENDPOINT_URL: str = ""

    # ── Kaggle ────────────────────────────────────────────────────────────────
    KAGGLE_API_TOKEN: str = ""

    # ── Reconciliation ────────────────────────────────────────────────────────
    SETTLEMENT_WINDOW_DAYS: int = 3
    FEE_TOLERANCE_MAX: float = 0.03   # 3% maximum fee
    MAX_ROWS_PER_UPLOAD: int = 50_000


settings = Settings()
