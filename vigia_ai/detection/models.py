from enum import StrEnum

from pydantic import BaseModel

from vigia_ai.fusion.models import EvidenceStrength


class IncidentState(StrEnum):
    SIN_EVIDENCIA = "SIN_EVIDENCIA"
    VIGILANCIA = "VIGILANCIA"
    ANOMALIA = "ANOMALIA"
    POSIBLE_IGNICION = "POSIBLE_IGNICION"
    PROBABLE_INCENDIO = "PROBABLE_INCENDIO"
    INCENDIO_CONFIRMADO = "INCENDIO_CONFIRMADO"
    DESCARTADO = "DESCARTADO"


class ReasonCode(StrEnum):
    MULTI_SENSOR_AGREEMENT = "MULTI_SENSOR_AGREEMENT"
    MULTI_FAMILY_AGREEMENT = "MULTI_FAMILY_AGREEMENT"
    TEMPORAL_PERSISTENCE = "TEMPORAL_PERSISTENCE"
    SPATIAL_CONSISTENCY = "SPATIAL_CONSISTENCY"
    FRP_INCREASE = "FRP_INCREASE"
    SINGLE_OBSERVATION = "SINGLE_OBSERVATION"
    SOURCE_CONTRADICTION = "SOURCE_CONTRADICTION"
    KNOWN_HEAT_SOURCE = "KNOWN_HEAT_SOURCE"
    STALE_DATA = "STALE_DATA"
    LOW_QUALITY = "LOW_QUALITY"
    INSUFFICIENT_INDEPENDENT_EVIDENCE = "INSUFFICIENT_INDEPENDENT_EVIDENCE"


class DetectionRecommendation(BaseModel):
    recommended_state: IncidentState
    evidence_strength: EvidenceStrength
    reason_codes: tuple[ReasonCode, ...]
    explanations: tuple[str, ...]
    missing_information: tuple[str, ...]
    rule_version: str
    calibrated_probability: None = None
