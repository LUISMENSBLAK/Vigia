from __future__ import annotations

from datetime import datetime
from typing import cast

from .models import ComponentEvidence, RiskAssessment, RiskDataQuality, RiskMode


class RiskEngine:
    """Combinación determinista, no calibrada y sin interpretación probabilística."""

    version = "risk-baseline-v1"
    required_component = "fire_weather"
    minimum_components = 2

    @staticmethod
    def _classify(value: float | None) -> str:
        if value is None:
            return "NO_DISPONIBLE"
        if value < 20.0:
            return "MUY_BAJO"
        if value < 40.0:
            return "BAJO"
        if value < 60.0:
            return "MODERADO"
        if value < 80.0:
            return "ALTO"
        return "MUY_ALTO"

    def assess(
        self,
        components: tuple[ComponentEvidence, ...],
        *,
        as_of: datetime,
        valid_at: datetime,
        mode: RiskMode,
    ) -> RiskAssessment:
        if valid_at < as_of and mode is RiskMode.FORECAST:
            raise ValueError("Un forecast no puede ser anterior a as_of")
        for component in components:
            if component.observed_at is not None and component.observed_at > as_of:
                raise ValueError(f"future leakage en {component.name}")
            if component.score is not None and not 0.0 <= component.score <= 100.0:
                raise ValueError(f"score fuera de rango en {component.name}")
        available = [component for component in components if component.score is not None]
        names = {component.name for component in available}
        missing = tuple(
            sorted(component.name for component in components if component.score is None)
        )
        reasons = sorted({code for component in components for code in component.reason_codes})
        if self.required_component not in names or len(available) < self.minimum_components:
            value = None
            quality = RiskDataQuality.INSUFFICIENT
            reasons.append("INSUFFICIENT_COMPONENTS_FOR_COMPOSITE")
        else:
            scores = [cast(float, component.score) for component in available]
            value = round(sum(scores) / len(scores), 6)
            quality = (
                RiskDataQuality.COMPLETE
                if not missing and all(c.quality is RiskDataQuality.COMPLETE for c in available)
                else RiskDataQuality.PARTIAL
            )
        explanations = tuple(
            f"{component.name}: {component.score:.2f}/100 ({component.source})"
            if component.score is not None
            else f"{component.name}: NO DISPONIBLE ({component.source})"
            for component in components
        )
        horizon = max(0, int((valid_at - as_of).total_seconds() // 3600))
        return RiskAssessment(
            engine_version=self.version,
            mode=mode,
            as_of=as_of,
            valid_at=valid_at,
            horizon_hours=horizon,
            experimental_index=value,
            risk_class=self._classify(value),
            data_quality=quality,
            components=components,
            missing_components=missing,
            reason_codes=tuple(sorted(set(reasons))),
            explanations=explanations,
        )


def normalized_fwi_component(value: float) -> float:
    """Escala de visualización monótona y acotada; no es probabilidad ni calibración."""
    if value < 0.0:
        raise ValueError("FWI no puede ser negativo")
    return 100.0 * value / (value + 20.0)


def normalized_ndmi_dryness(value: float) -> float:
    """Invierte el dominio físico NDMI [-1, 1] a una escala descriptiva [0, 100]."""
    if not -1.0 <= value <= 1.0:
        raise ValueError("NDMI debe estar entre -1 y 1")
    return 50.0 * (1.0 - value)


def normalized_slope_context(slope_deg: float) -> float:
    """Escala contextual acotada; no estima propagación."""
    if slope_deg < 0.0:
        raise ValueError("La pendiente no puede ser negativa")
    return min(100.0, slope_deg / 45.0 * 100.0)
