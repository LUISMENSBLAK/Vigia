import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, Field

from .models import SourceFamily

DEFAULT_CONFIG_PATH = Path("config/fusion.v1.json")


class SourceProfile(BaseModel):
    spatial_resolution_m: float = Field(gt=0)
    association_radius_m: float = Field(gt=0)
    max_temporal_gap_minutes: int = Field(gt=0)


class FusionConfig(BaseModel):
    version: str
    rule_version: str
    max_age_minutes: int = Field(gt=0)
    persistence_window_minutes: int = Field(gt=0)
    candidate_expiration_minutes: int = Field(gt=0)
    incident_min_observations: int = Field(ge=2)
    possible_ignition_min_observations: int = Field(ge=2)
    possible_ignition_min_persistence_minutes: int = Field(ge=0)
    probable_fire_min_observations: int = Field(ge=2)
    probable_fire_min_thermal_families: int = Field(ge=2)
    probable_fire_min_persistence_minutes: int = Field(ge=0)
    source_profiles: dict[SourceFamily, SourceProfile]

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )

    @property
    def configuration_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()

    @property
    def maximum_association_radius_m(self) -> float:
        return max(profile.association_radius_m for profile in self.source_profiles.values())


def load_fusion_config(path: Path = DEFAULT_CONFIG_PATH) -> FusionConfig:
    return FusionConfig.model_validate_json(path.read_text(encoding="utf-8"))
