from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import rasterio

from vigia_geospatial.products import DerivedRaster, array_to_cog


@dataclass(frozen=True, slots=True)
class RiskGridComponent:
    name: str
    values: np.ndarray
    transform: rasterio.Affine
    crs: str
    resolution_m: float
    observed_at: str | None
    source: str


def _validate_alignment(components: tuple[RiskGridComponent, ...]) -> None:
    if not components:
        raise ValueError("Se requiere al menos una componente raster.")
    reference = components[0]
    if reference.values.ndim != 2 or reference.resolution_m <= 0.0:
        raise ValueError("Componente raster de referencia no válida.")
    for component in components:
        if component.values.shape != reference.values.shape:
            raise ValueError("Las componentes no comparten dimensiones.")
        if component.crs != reference.crs or component.transform != reference.transform:
            raise ValueError("Las componentes no están alineadas en CRS y transform.")
        if not np.isclose(component.resolution_m, reference.resolution_m):
            raise ValueError("No se pueden mezclar resoluciones silenciosamente.")


def build_risk_cogs(
    components: tuple[RiskGridComponent, ...],
    *,
    required_component: str = "fire_weather",
    minimum_components: int = 2,
) -> tuple[DerivedRaster, DerivedRaster]:
    """Crea índice y calidad; nodata permanece nodata y no se imputa."""
    _validate_alignment(components)
    by_name = {component.name: component for component in components}
    if len(by_name) != len(components) or required_component not in by_name:
        raise ValueError("Componentes duplicadas o falta la componente crítica.")
    for component in components:
        finite = component.values[np.isfinite(component.values)]
        if finite.size and (float(finite.min()) < 0.0 or float(finite.max()) > 100.0):
            raise ValueError(f"La componente {component.name} sale de [0, 100].")
    stack = np.stack([component.values.astype("float64") for component in components])
    valid = np.isfinite(stack)
    valid_count = valid.sum(axis=0)
    required_valid = np.isfinite(by_name[required_component].values)
    allowed = required_valid & (valid_count >= minimum_components)
    composite = np.divide(
        np.nansum(stack, axis=0),
        valid_count,
        out=np.full(stack.shape[1:], np.nan),
        where=allowed,
    )
    composite[~allowed] = np.nan
    quality = valid_count.astype("float64") / len(components) * 100.0
    quality[~required_valid] = np.nan
    reference = components[0]
    provenance: dict[str, Any] = {
        "components": [
            {
                "name": item.name,
                "source": item.source,
                "observed_at": item.observed_at,
                "resolution_m": item.resolution_m,
            }
            for item in components
        ],
        "required_component": required_component,
        "minimum_components": minimum_components,
        "unweighted": True,
        "probability": False,
    }
    risk = array_to_cog(
        composite,
        transform=reference.transform,
        crs=reference.crs,
        layer="RISK_BASELINE",
        units="experimental_index_0_100",
        algorithm="unweighted_available_component_mean_v1",
        quality=provenance,
        resampling="nearest",
    )
    data_quality = array_to_cog(
        quality,
        transform=reference.transform,
        crs=reference.crs,
        layer="RISK_DATA_QUALITY",
        units="available_component_percent",
        algorithm="available_component_fraction_v1",
        quality=provenance,
        resampling="nearest",
    )
    return risk, data_quality
