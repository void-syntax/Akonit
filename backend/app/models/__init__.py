"""All SQLAlchemy models. Importing this module registers every table."""

# Re-export the enums from a submodule so mapped_column(Enum) resolves them by
# name across the registry regardless of import order.
from app.models.enums import (  # noqa: F401  (import first on purpose)
    ConditionOperator,
    ConditionType,
    DeliveryStatus,
    JoinType,
    NotificationChannel,
    NotificationFrequency,
    SignalStatus,
    SourceStatus,
    SourceType,
)
from app.db.session import Base  # noqa: F401
from app.models.notifications import (
    IgnoredSignal,
    NotificationDelivery,
    NotificationPreference,
    SavedSignal,
    SourceHealth,
)
from app.models.radars import (
    Radar,
    RadarCondition,
    RadarConditionGroup,
    RadarSignal,
)
from app.models.signals import Signal, SignalSnapshot
from app.models.tags import CustomTag, SignalTag, Tag, TagAlias
from app.models.taxonomy import Country, Source, SourceEvent
from app.models.user import User, UserProfile
from app.pipeline.dlq import FailedSignal

__all__ = [
    "Base",
    "User",
    "UserProfile",
    "Country",
    "Source",
    "SourceEvent",
    "Tag",
    "TagAlias",
    "CustomTag",
    "SignalTag",
    "Signal",
    "SignalSnapshot",
    "FailedSignal",
    "Radar",
    "RadarConditionGroup",
    "RadarCondition",
    "RadarSignal",
    "SavedSignal",
    "IgnoredSignal",
    "NotificationPreference",
    "NotificationDelivery",
    "SourceHealth",
    "SignalStatus",
    "NotificationFrequency",
    "NotificationChannel",
    "SourceStatus",
    "SourceType",
    "DeliveryStatus",
    "ConditionType",
    "ConditionOperator",
    "JoinType",
]