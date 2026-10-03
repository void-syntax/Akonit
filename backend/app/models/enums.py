"""Shared enums and helpers for models.

All string enums accept lowercase input (the frontend sends `"country"`,
`"instant"`, ...), so casing never becomes a source of bugs.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


class CaseInsensitiveEnum(str, enum.Enum):
    """Base for enums whose members load from lowercase API payloads."""

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            wanted = value.strip().lower()
            for member in cls:
                if member.value.lower() == wanted or member.name.lower() == wanted:
                    return member
        return None


def uuid_str() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


def ts_column(**kw):
    return mapped_column(DateTime(timezone=True), **kw)


class SignalStatus(CaseInsensitiveEnum):
    NEW = "NEW"
    RISING = "RISING"
    BREAKOUT = "BREAKOUT"
    FADING = "FADING"


class NotificationFrequency(CaseInsensitiveEnum):
    OFF = "OFF"
    INSTANT = "INSTANT"
    EVERY_15_MIN = "EVERY_15_MIN"
    HOURLY = "HOURLY"
    DAILY_DIGEST = "DAILY_DIGEST"


class NotificationChannel(CaseInsensitiveEnum):
    WEB_PUSH = "WEB_PUSH"
    TELEGRAM = "TELEGRAM"


class SourceStatus(CaseInsensitiveEnum):
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    OPTIONAL_CREDENTIALS = "OPTIONAL_CREDENTIALS"


class SourceType(CaseInsensitiveEnum):
    SOCIAL = "SOCIAL"
    TREND = "TREND"
    DEVELOPER = "DEVELOPER"
    PRODUCT = "PRODUCT"
    COMMUNITY = "COMMUNITY"
    NEWS = "NEWS"
    RSS = "RSS"


class DeliveryStatus(CaseInsensitiveEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ConditionType(CaseInsensitiveEnum):
    COUNTRY = "COUNTRY"
    SOURCE = "SOURCE"
    TAG = "TAG"
    KEYWORD = "KEYWORD"
    GROWTH = "GROWTH"
    ACTIVITY = "ACTIVITY"
    AGE = "AGE"
    STATUS = "STATUS"
    STRENGTH = "STRENGTH"


class ConditionOperator(CaseInsensitiveEnum):
    IN = "IN"
    NOT_IN = "NOT_IN"
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    EQ = "EQ"
    CONTAINS = "CONTAINS"


class JoinType(CaseInsensitiveEnum):
    AND = "AND"
    OR = "OR"
    NOT = "NOT"