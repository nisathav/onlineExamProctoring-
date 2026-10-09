"""Application settings, read from environment variables only."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"  # development | production | test

    # Security
    secret_key: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Database
    database_url: str = "postgresql+psycopg2://proctor:proctor@db:5432/proctoring"

    # MinIO
    minio_endpoint: str = "minio:9000"
    minio_public_endpoint: str = ""  # host:port used in presigned URLs for the browser
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "evidence"
    minio_secure: bool = False
    minio_public_secure: bool = False  # https for presigned URLs (behind the TLS proxy)
    presigned_url_expiry_seconds: int = 300

    # ML (thesis values; do not change without being asked)
    gaze_model_path: str = "models/gaze_model.keras"
    gaze_threshold: float = 0.5
    capture_interval_seconds: int = 3
    ml_workers: int = 4

    # Temporal analysis (Phase 7)
    flag_away_count: int = 3
    # Auto-pause the exam after this many looking-away detections (counted since the
    # attempt started or since staff last let the student continue). 0 disables it.
    pause_after_away_count: int = 3
    flag_window_seconds: int = 30
    long_away_seconds: int = 15

    # Hardening (Phase 8)
    frontend_origin: str = "http://localhost:3000"
    max_frame_bytes: int = 2 * 1024 * 1024
    login_rate_limit: int = 10  # attempts
    login_rate_window_seconds: int = 60
    evidence_retention_days: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
