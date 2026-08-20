"""Historical reference corpus isolated from VIGÍA engine inputs."""

from .jcyl import JCYL_DATASET_URL, build_jcyl_corpus, select_pilot_events
from .models import (
    HistoricalFireEvent,
    HistoricalFireReference,
    HistoricalTimestamp,
    ReferenceQuality,
    TimestampPrecision,
)

__all__ = [
    "JCYL_DATASET_URL",
    "HistoricalFireEvent",
    "HistoricalFireReference",
    "HistoricalTimestamp",
    "ReferenceQuality",
    "TimestampPrecision",
    "build_jcyl_corpus",
    "select_pilot_events",
]
