from datetime import datetime

from vigia_ai.fusion.config import FusionConfig
from vigia_ai.fusion.models import (
    THERMAL_SOURCE_FAMILIES,
    DataQuality,
    EvidenceRole,
    EvidenceStrength,
    IncidentCandidate,
    SourceFamily,
)

from .models import DetectionRecommendation, IncidentState, ReasonCode


def _frp_is_increasing(candidate: IncidentCandidate) -> bool:
    observations = [
        item.observation
        for item in candidate.observations
        if item.role is EvidenceRole.CONFIRMING and item.observation.frp_mw is not None
    ]
    ordered = sorted(observations, key=lambda item: item.observed_at)
    if len(ordered) < 2:
        return False
    first = ordered[0].frp_mw
    last = ordered[-1].frp_mw
    return first is not None and last is not None and last > first


def recommend_state(
    candidate: IncidentCandidate,
    *,
    config: FusionConfig,
    as_of: datetime,
) -> DetectionRecommendation:
    if as_of.tzinfo is None:
        raise ValueError("as_of debe incluir zona horaria.")
    confirming = [
        item for item in candidate.observations if item.role is EvidenceRole.CONFIRMING
    ]
    contradictions = [
        item for item in candidate.observations if item.role is EvidenceRole.CONTRADICTING
    ]
    thermal_families = {
        item.observation.source_family
        for item in confirming
        if item.observation.source_family in THERMAL_SOURCE_FAMILIES
    }
    reason_codes: list[ReasonCode] = [ReasonCode.SPATIAL_CONSISTENCY]
    explanations = [
        f"{len(confirming)} observaciones térmicas compatibles",
        f"{len(candidate.platforms)} plataformas y {len(candidate.sensors)} sensores",
        f"persistencia observada de {candidate.persistence.persistence_seconds // 60} min",
        f"coherencia espacial dentro de {round(candidate.spatial_extent_m)} m del centroide",
    ]
    missing: list[str] = []

    if len(confirming) == 1:
        reason_codes.append(ReasonCode.SINGLE_OBSERVATION)
    if len(candidate.sensors) > 1 or len(candidate.platforms) > 1:
        reason_codes.append(ReasonCode.MULTI_SENSOR_AGREEMENT)
    if len(thermal_families) > 1:
        reason_codes.append(ReasonCode.MULTI_FAMILY_AGREEMENT)
    else:
        reason_codes.append(ReasonCode.INSUFFICIENT_INDEPENDENT_EVIDENCE)
        missing.append("segunda familia térmica aproximadamente independiente")
    if candidate.persistence.persistence_seconds >= (
        config.possible_ignition_min_persistence_minutes * 60
    ):
        reason_codes.append(ReasonCode.TEMPORAL_PERSISTENCE)
    if _frp_is_increasing(candidate):
        reason_codes.append(ReasonCode.FRP_INCREASE)
        explanations.append("FRP creciente en observaciones que disponen de ese campo")
    if contradictions:
        reason_codes.append(ReasonCode.SOURCE_CONTRADICTION)
        explanations.append(f"{len(contradictions)} evidencias contradictorias")
    if any("KNOWN_HEAT_SOURCE" in item.reason_codes for item in contradictions):
        reason_codes.append(ReasonCode.KNOWN_HEAT_SOURCE)
    if candidate.data_quality in {DataQuality.DEGRADADA, DataQuality.DESCONOCIDA}:
        reason_codes.append(ReasonCode.LOW_QUALITY)
    if not any(
        item.observation.source_family is SourceFamily.AEMET_WEATHER
        for item in candidate.observations
    ):
        missing.append("meteorología contextual")

    is_stale = (as_of - candidate.last_observation_at).total_seconds() > (
        config.candidate_expiration_minutes * 60
    )
    if is_stale:
        reason_codes.append(ReasonCode.STALE_DATA)

    probable = (
        len(confirming) >= config.probable_fire_min_observations
        and len(thermal_families) >= config.probable_fire_min_thermal_families
        and candidate.persistence.persistence_seconds
        >= config.probable_fire_min_persistence_minutes * 60
        and not contradictions
        and candidate.data_quality is not DataQuality.DEGRADADA
        and not is_stale
    )
    possible = (
        len(confirming) >= config.possible_ignition_min_observations
        and candidate.persistence.persistence_seconds
        >= config.possible_ignition_min_persistence_minutes * 60
        and not is_stale
    )
    if contradictions and not confirming:
        state = IncidentState.DESCARTADO
        strength = EvidenceStrength.MUY_BAJA
    elif probable:
        state = IncidentState.PROBABLE_INCENDIO
        strength = EvidenceStrength.MUY_ALTA
    elif possible:
        state = IncidentState.POSIBLE_IGNICION
        strength = EvidenceStrength.ALTA
    elif len(confirming) >= config.incident_min_observations and not is_stale:
        state = IncidentState.ANOMALIA
        strength = EvidenceStrength.MEDIA
    else:
        state = IncidentState.VIGILANCIA
        strength = EvidenceStrength.BAJA if confirming else EvidenceStrength.MUY_BAJA

    return DetectionRecommendation(
        recommended_state=state,
        evidence_strength=strength,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        explanations=tuple(explanations),
        missing_information=tuple(missing),
        rule_version=config.rule_version,
    )
