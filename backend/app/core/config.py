"""Application settings.

Thresholds, weights and intervals live here so detection is configurable
and never hardcoded inside business logic.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- app ---
    app_env: str = "development"
    api_debug: bool = True
    secret_key: str = "change-me-to-a-long-random-string"
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    # --- infra ---
    database_url: str = "sqlite+aiosqlite:///./signal_radar.db"
    redis_url: str | None = None
    db_echo: bool = False

    # --- auth ---
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 30

    # --- sources / collectors ---
    github_token: str | None = None
    hf_token: str | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str = "SignalRadar/0.1"
    youtube_api_key: str | None = None
    tiktok_api_token: str | None = None
    instagram_access_token: str | None = None
    meta_app_id: str | None = None
    meta_app_secret: str | None = None

    collect_interval_seconds: int = 900
    snapshot_interval_seconds: int = 900
    fetch_timeout_seconds: int = 30
    http_user_agent: str = (
        "SignalRadarBot/0.1 (+https://github.com/signal-radar) "
        "Mozilla/5.0 (compatible; SignalRadar/0.1)"
    )
    http_max_concurrency: int = 8

    # --- detection (configurable) ---
    detect_min_strength: float = 35.0
    detect_rising_strength: float = 45.0
    detect_breakout_strength: float = 70.0
    detect_fading_drop_ratio: float = 0.6
    detect_min_age_minutes: int = 0
    detect_dedup_window_minutes: int = 60
    detect_early_bonus_max: float = 25.0
    detect_persistence_windows: int = 2
    detect_min_absolute_activity: float = 5.0

    # scoring weights (sum to 100)
    weight_growth: float = 26.0
    weight_acceleration: float = 24.0
    weight_recency: float = 20.0
    weight_absolute: float = 12.0
    weight_persistence: float = 10.0
    weight_cross_source: float = 8.0

    # --- notifications ---
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@example.com"
    telegram_bot_token: str | None = None

    # --- matching ---
    fuzzy_match_threshold: float = 0.86
    dedup_similarity_threshold: float = 0.82

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def public_dict(self) -> dict[str, Any]:
        safe = {}
        for key, value in self.model_dump().items():
            if any(s in key for s in ("token", "secret", "password", "key")):
                if value:
                    safe[key] = "***set***"
                else:
                    safe[key] = None
            else:
                safe[key] = value
        return safe


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()