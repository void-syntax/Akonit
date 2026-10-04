"""Pydantic schemas for the API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import (
    NotificationChannel,
    NotificationFrequency,
    SignalStatus,
    SourceStatus,
    SourceType,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(ORMModel):
    id: str
    email: str
    is_active: bool
    created_at: datetime


class ProfileOut(ORMModel):
    display_name: str | None
    timezone: str
    language: str
    telegram_chat_id: str | None
    default_frequency: NotificationFrequency
    onboarded: bool
    signal_threshold: float = 0.0
    default_countries: list[str] = Field(default_factory=list)
    default_sources: list[str] = Field(default_factory=list)
    default_tags: list[str] = Field(default_factory=list)
    quiet_hours: dict[str, Any] | None = None
    theme: str = "dark"


# ---------------------------------------------------------- taxonomy
class CountryOut(ORMModel):
    code: str
    alpha3: str
    name: str
    slug: str
    flag: str
    region: str | None
    is_supported: bool


class SourceOut(ORMModel):
    id: str
    name: str
    type: SourceType
    description: str | None
    enabled: bool
    status: SourceStatus
    status_reason: str | None
    cost: str
    credentials_required: bool
    capabilities: list[str]
    priority: int
    strategy: str | None
    last_fetch: datetime | None
    last_success: datetime | None
    records_fetched: int
    total_records: int
    error_count: int
    last_error: str | None


class TagOut(ORMModel):
    slug: str
    name: str
    category: str
    emoji: str | None
    description: str | None


class CustomTagCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    keywords: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    country_codes: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)
    exclude_hashtags: list[str] = Field(default_factory=list)
    exclude_countries: list[str] = Field(default_factory=list)
    emoji: str | None = None


class CustomTagOut(ORMModel):
    id: str
    name: str
    slug: str
    keywords: list[str]
    aliases: list[str]
    hashtags: list[str]
    country_codes: list[str]
    source_ids: list[str]
    excludes: list[str]
    exclude_hashtags: list[str]
    exclude_countries: list[str]
    emoji: str | None
    is_active: bool
    created_at: datetime


# ------------------------------------------------------------ signals
class SignalOut(ORMModel):
    id: str
    title: str
    description: str
    category: str | None
    hashtags: list[str]
    country_code: str | None
    country_name: str | None
    flag: str | None
    source_id: str
    source_url: str
    thumbnail: str | None
    cross_source_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    current_activity: float
    previous_activity: float
    growth: float
    acceleration: float
    status: SignalStatus
    strength: float
    age_minutes: float
    activity_metric: str | None
    keywords: list[str]
    is_saved: bool = False
    is_ignored: bool = False


class SnapshotOut(ORMModel):
    captured_at: datetime
    activity: float
    previous_activity: float
    growth: float
    acceleration: float
    strength: float
    status: SignalStatus
    rank: int | None


class SignalDetail(SignalOut):
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    snapshots: list[SnapshotOut] = Field(default_factory=list)


class SignalPage(BaseModel):
    items: list[SignalOut]
    total: int
    limit: int
    offset: int


# ------------------------------------------------------------- radars
class RadarCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    emoji: str | None = None
    description: str | None = None
    conditions: dict[str, Any] | list[dict[str, Any]]
    signal_threshold: float = 0.0
    notification_frequency: NotificationFrequency = NotificationFrequency.INSTANT
    notification_channels: list[str] = Field(default_factory=lambda: ["WEB_PUSH"])


class RadarUpdate(BaseModel):
    name: str | None = None
    emoji: str | None = None
    description: str | None = None
    conditions: dict[str, Any] | list[dict[str, Any]] | None = None
    signal_threshold: float | None = None
    notification_frequency: NotificationFrequency | None = None
    notification_channels: list[str] | None = None
    is_active: bool | None = None


class RadarOut(ORMModel):
    id: str
    name: str
    emoji: str | None
    description: str | None
    countries: list[str]
    source_ids: list[str]
    tag_slugs: list[str]
    signal_threshold: float
    notification_frequency: NotificationFrequency
    notification_channels: list[str]
    is_active: bool
    match_count: int
    active_signal_count: int = 0
    last_matched_at: datetime | None
    created_at: datetime


class ConditionOption(BaseModel):
    type: str
    operators: list[str]
    unit_options: list[str] | None = None
    description: str


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    timezone: str | None = None
    language: str | None = None
    telegram_chat_id: str | None = None
    default_frequency: NotificationFrequency | None = None
    signal_threshold: float | None = None
    default_countries: list[str] | None = None
    default_sources: list[str] | None = None
    default_tags: list[str] | None = None
    quiet_hours: dict[str, Any] | None = None
    theme: str | None = None


class PushSubscribeRequest(BaseModel):
    endpoint: str
    keys: dict[str, str] = Field(default_factory=dict)
    radar_id: str | None = None


class PushUnsubscribeRequest(BaseModel):
    endpoint: str