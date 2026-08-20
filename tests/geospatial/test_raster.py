from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from vigia_geospatial.crs import etrs89_utm_for_mainland, require_projected_metric_crs
from vigia_geospatial.raster import (
    create_cog,
    derive_terrain,
    validate_metric_raster_crs,
    validate_raster,
)


def make_raster(path: Path) -> None:
    values = np.arange(1024, dtype="float32").reshape(32, 32)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=32,
        height=32,
        count=1,
        dtype="float32",
        crs="EPSG:25830",
        transform=from_origin(350_000, 4_600_000, 10, 10),
        nodata=-9999,
    ) as output:
        output.write(values, 1)


def test_raster_validation_and_cog_metadata(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    destination = tmp_path / "result.cog.tif"
    make_raster(source)

    raw = validate_raster(source)
    cog = create_cog(source, destination)

    assert raw.crs == "EPSG:25830"
    assert raw.resolution == (10.0, 10.0)
    assert raw.nodata == -9999
    assert cog.is_cog is True
    assert cog.tiled is True
    assert len(cog.checksum_sha256) == 64
    assert validate_metric_raster_crs(destination) == "EPSG:25830"


def test_corrupt_raster_is_rejected(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.tif"
    corrupt.write_bytes(b"not-a-raster")
    with pytest.raises(ValueError, match="corrupto"):
        validate_raster(corrupt)


def test_terrain_derivatives_preserve_nodata() -> None:
    elevation = np.array([[100, 101, 102], [101, np.nan, 103], [102, 103, 104]], dtype="float32")
    derived = derive_terrain(elevation, resolution_x_m=10, resolution_y_m=10)

    assert set(derived) == {"slope_degrees", "aspect_degrees", "ruggedness_m"}
    assert np.isnan(derived["slope_degrees"][1, 1])
    assert np.nanmin(derived["slope_degrees"]) >= 0
    assert np.nanmax(derived["slope_degrees"]) <= 90


def test_crs_strategy_uses_metric_etrs89_and_rejects_geographic_analysis() -> None:
    assert etrs89_utm_for_mainland(-4.7, 40.65).to_epsg() == 25830
    assert etrs89_utm_for_mainland(-9.0, 42.0).to_epsg() == 25829
    with pytest.raises(ValueError, match="proyectado"):
        require_projected_metric_crs("EPSG:4326")
    with pytest.raises(ValueError, match="Fuera"):
        etrs89_utm_for_mainland(-16.0, 28.3)
