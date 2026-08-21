"""Scientific validation contracts, isolated from operational detection."""

from .datasets import build_corpus_version, validation_event
from .matching import match_events
from .models import HistoricalCorpusVersion, ValidationReport, ValidationSplitManifest
from .splits import frozen_temporal_group_split

__all__ = [
    "HistoricalCorpusVersion",
    "ValidationReport",
    "ValidationSplitManifest",
    "build_corpus_version",
    "frozen_temporal_group_split",
    "match_events",
    "validation_event",
]
