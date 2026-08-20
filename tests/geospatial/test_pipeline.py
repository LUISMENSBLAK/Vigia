from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from vigia_geospatial.aoi import AOIRequest, resolve_inline_aoi
from vigia_geospatial.models import AvailabilityState, GeospatialLayer
from vigia_geospatial.pipeline import RasterCatalogItem, ingest_raster_bytes
from vigia_geospatial.storage import LocalStorage


def raster_bytes() -> bytes:
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            width=16,
            height=16,
            count=1,
            dtype="float32",
            crs="EPSG:25830",
            transform=from_origin(350_000, 4_600_000, 10, 10),
            nodata=-9999,
        ) as dataset:
            dataset.write(np.ones((16, 16), dtype="float32"), 1)
        return memory.read()


def test_pipeline_creates_raw_cog_manifest_and_reproducible_cache(tmp_path: Path) -> None:
    aoi = resolve_inline_aoi(AOIRequest(bbox=(-4.8, 40.6, -4.6, 40.8)))
    item = RasterCatalogItem(
        provider="OFFICIAL TEST PROVIDER",
        dataset="SYNTHETIC TEST DATA",
        product_id="TEST-PRODUCT-001",
        source_uri="https://example.invalid/product/001",
        observed_at=datetime(2026, 8, 19, tzinfo=UTC),
        footprint_geojson=aoi.geojson,
        source_resolution_m=10,
        source_crs="EPSG:25830",
        quality={"test_only": True},
        etag="test-etag",
    )
    storage = LocalStorage(tmp_path / "storage")
    arguments = {
        "item": item,
        "layer": GeospatialLayer.ELEVATION,
        "aoi": aoi,
        "content": raster_bytes(),
        "storage": storage,
        "configuration_hash": "a" * 64,
        "software_version": "test",
        "algorithm": "identity-test-only",
        "request_id": "test-run",
    }

    first = ingest_raster_bytes(**arguments)
    second = ingest_raster_bytes(**arguments)

    assert first.product.availability is AvailabilityState.AVAILABLE
    assert first.product.output_hash == second.product.output_hash
    assert first.product.storage_uri == second.product.storage_uri
    assert first.manifest.checksum_sha256 == second.manifest.checksum_sha256
    assert first.product.quality["cog"] is True
    assert first.product.output_resolution_m == 10
    assert len(list((tmp_path / "storage").rglob("*.tif"))) == 2
