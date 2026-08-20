import json
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from vigia_geospatial.materialize import load_materialization_config, resolved_aoi
from vigia_geospatial.serving import render_tile, sample_raster


def test_real_aoi_configuration_is_generic_and_includes_second_province() -> None:
    config = load_materialization_config(
        Path("config/geospatial/avila-tile-356-4502.json")
    )
    codes = {unit.national_code for unit in config.administrative_units}

    assert config.id == "es-avila-pnoa-356-4502-h30"
    assert "34070500000" in codes
    assert "34074000000" in codes
    assert resolved_aoi(config).geometry.area > 0


def test_changing_province_is_configuration_only(tmp_path: Path) -> None:
    payload = json.loads(
        Path("config/geospatial/avila-tile-356-4502.json").read_text(encoding="utf-8")
    )
    payload["id"] = "segovia-validation-aoi"
    payload["bounds"] = [400000, 4520000, 401000, 4521000]
    path = tmp_path / "segovia.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    config = load_materialization_config(path)
    assert config.id == "segovia-validation-aoi"
    assert config.bounds == (400000, 4520000, 401000, 4521000)


def test_configuration_rejects_parent_outside_hierarchy(tmp_path: Path) -> None:
    payload = json.loads(
        Path("config/geospatial/avila-tile-356-4502.json").read_text(encoding="utf-8")
    )
    payload["administrative_units"][-1]["parent"] = "99999999999"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValidationError, match="parent administrativo"):
        load_materialization_config(path)


def test_point_sampling_and_tile_rendering_use_real_raster_metadata(tmp_path: Path) -> None:
    path = tmp_path / "terrain.tif"
    values = np.arange(256, dtype="float32").reshape(16, 16)
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            width=16,
            height=16,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(-4.8, 41.0, 0.01, 0.01),
            nodata=-9999,
        ) as dataset:
            dataset.write(values, 1)
        path.write_bytes(memory.read())
    uri = path.resolve().as_uri()

    sampled = sample_raster(
        uri, longitude=-4.795, latitude=40.995, band=1, storage_root=tmp_path
    )
    tile = render_tile(
        uri, band=1, layer="ELEVATION", z=6, x=31, y=23, storage_root=tmp_path
    )

    assert sampled == pytest.approx(0)
    assert tile.startswith(b"\x89PNG\r\n\x1a\n")
