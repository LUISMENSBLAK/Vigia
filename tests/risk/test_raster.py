import numpy as np
import pytest
from rasterio.transform import from_origin

from vigia_ai.risk.raster import RiskGridComponent, build_risk_cogs


def _component(
    name: str, values: list[list[float]], resolution: float = 100.0
) -> RiskGridComponent:
    return RiskGridComponent(
        name=name,
        values=np.asarray(values, dtype="float64"),
        transform=from_origin(300000.0, 4500000.0, resolution, resolution),
        crs="EPSG:25830",
        resolution_m=resolution,
        observed_at="2026-08-20T10:00:00Z",
        source="TEST_FIXTURE",
    )


def test_builds_valid_cogs_and_preserves_missing_critical_pixels() -> None:
    weather = _component("fire_weather", [[60.0, np.nan], [40.0, 80.0]])
    vegetation = _component("vegetation", [[20.0, 20.0], [np.nan, 40.0]])
    terrain = _component("terrain", [[40.0, 40.0], [20.0, 60.0]])
    risk, quality = build_risk_cogs((weather, vegetation, terrain))
    assert risk.validation.is_cog is True
    assert risk.quality["valid_pixels"] == 3
    assert risk.quality["probability"] is False
    assert quality.validation.is_cog is True


def test_rejects_silent_resolution_mixing() -> None:
    weather = _component("fire_weather", [[50.0]], 100.0)
    terrain = _component("terrain", [[50.0]], 200.0)
    with pytest.raises(ValueError, match="dimensiones|alineadas|resoluciones"):
        build_risk_cogs((weather, terrain))


def test_rejects_out_of_range_component() -> None:
    with pytest.raises(ValueError, match="sale de"):
        build_risk_cogs((_component("fire_weather", [[101.0]]), _component("terrain", [[50.0]])))
