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
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    # --- infra ---
    # Postgres is the default so a fresh checkout with `docker compose up` works
    # without editing anything. SQLite remains available for a zero-dependency
    # trial run, but it is not what the local stack uses.
    database_url: str = "postgresql+asyncpg://signal:signal@localhost:5432/signal_radar"
    redis_url: str | None = None
    db_echo: bool = False

    # --- auth ---
    # There is no login: the app runs on the operator's own machine, so the API
    # resolves one local account and every request uses it. `auth_disabled=false`
    # turns token auth back on for anyone who puts this behind a shared host.
    auth_disabled: bool = True
    local_user_email: str = "local@signalradar"

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

    # A minute is the point of the product: the whole promise is catching things
    # while they are still early, so the worker runs as often as it reasonably
    # can on the machine it is running on.
    collect_interval_seconds: int = 60
    snapshot_interval_seconds: int = 300
    fetch_timeout_seconds: int = 30
    source_cooldown_seconds: int = 300
    http_user_agent: str = (
        "SignalRadarBot/0.1 (+https://github.com/signal-radar) "
        "Mozilla/5.0 (compatible; SignalRadar/0.1)"
    )
    # Keep the request pool small so a laptop can collect without bursts of
    # sockets, memory and CPU. Individual collectors still run concurrently.
    http_max_concurrency: int = 4
    collection_max_events_per_source: int = 25
    ai_classification_enabled: bool = False

    # --- tag-driven collection ---
    # Countries to cover before the user configures any radar, so a fresh
    # install still collects real data instead of nothing.
    default_collect_countries: list[str] = ["US", "GB", "KR", "JP", "DE", "BR"]
    # Cap on queries handed to the collectors per run. More is slower and gets
    # rate-limited, and past a handful the marginal signal is noise.
    max_collect_keywords: int = 8

    # --- detection (configurable) ---
    detect_min_strength: float = 35.0
    detect_rising_strength: float = 45.0
    detect_breakout_strength: float = 70.0
    detect_fading_drop_ratio: float = 0.6
    detect_dedup_window_minutes: int = 60
    detect_early_bonus_max: float = 25.0
    detect_persistence_windows: int = 2
    detect_min_absolute_activity: float = 5.0
    # Smoothed velocity a signal must exceed before it can be called a breakout.
    detect_breakout_velocity: float = 40.0
    # Hard freshness cutoff, applied at ingestion. Search-driven collectors keep
    # surfacing evergreen hits that look new; this is what stops a five-year-old
    # video from entering the feed as a breaking trend. 0 disables the filter.
    detect_max_age_hours: int = 72
    # Strength margin required before an established signal is demoted, which
    # stops a single noisy window from flipping it back and forth.
    detect_hysteresis: float = 8.0

    # scoring weights (sum to 100)
    weight_growth: float = 18.0
    weight_velocity: float = 22.0
    weight_acceleration: float = 16.0
    weight_recency: float = 14.0
    weight_absolute: float = 8.0
    weight_persistence: float = 12.0
    weight_cross_source: float = 10.0

    # --- notifications ---
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@example.com"
    telegram_bot_token: str | None = None
    telegram_token_encryption_key: str | None = None

    # --- retention ---
    # A signal is only interesting while it is fresh. Anything a user saved is
    # kept forever; everything else disappears once it expires.
    signal_ttl_hours: int = 24
    source_event_ttl_hours: int = 48
    delivery_ttl_days: int = 30
    cleanup_batch_size: int = 2000
    cleanup_max_rows_per_run: int = 10000
    cleanup_interval_minutes: int = 60

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
