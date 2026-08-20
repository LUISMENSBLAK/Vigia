from datetime import UTC, datetime
from pathlib import Path

import laspy
import numpy as np
import pytest
from pydantic import ValidationError
from pyproj import CRS

from vigia_geospatial.lidar import validate_las_laz
from vigia_geospatial.models import AvailabilityState, DownloadManifest
from vigia_geospatial.storage import LocalStorage
from vigia_geospatial.vegetation import sentinel2_indices, sentinel2_valid_mask


def test_local_storage_is_idempotent_and_confined(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "objects")
    first_uri, first_hash = storage.put("sentinel/product.tif", b"same-content")
    second_uri, second_hash = storage.put("sentinel/product.tif", b"same-content")

    assert first_uri == second_uri
    assert first_hash == second_hash
    assert storage.exists("sentinel/product.tif")
    with pytest.raises(ValueError, match="no válida"):
        storage.put("../secret", b"blocked")


def test_sentinel_indices_mask_cloud_shadow_and_nodata() -> None:
    red = np.array([[0.2, 0.2], [0.2, 0.0]], dtype="float32")
    nir = np.array([[0.6, 0.7], [0.8, 0.0]], dtype="float32")
    swir11 = np.array([[0.3, 0.3], [0.4, 0.0]], dtype="float32")
    swir12 = np.array([[0.4, 0.4], [0.5, 0.0]], dtype="float32")
    scl = np.array([[4, 9], [3, 4]], dtype="uint8")
    data_mask = np.ones((2, 2), dtype="uint8")

    valid = sentinel2_valid_mask(scl, data_mask)
    indices = sentinel2_indices(
        red_b04=red,
        nir_b08=nir,
        swir_b11=swir11,
        swir_b12=swir12,
        scl=scl,
        data_mask=data_mask,
    )

    assert valid.tolist() == [[True, False], [False, True]]
    assert indices["ndvi"][0, 0] == pytest.approx(0.5)
    assert indices["ndmi"][0, 0] == pytest.approx(1 / 3)
    assert indices["nbr"][0, 0] == pytest.approx(0.2)
    assert np.isnan(indices["ndvi"][0, 1])
    assert np.isnan(indices["ndvi"][1, 1])


def test_lidar_header_validation_preserves_crs_and_bounds(tmp_path: Path) -> None:
    path = tmp_path / "tiny.las"
    header = laspy.LasHeader(point_format=3, version="1.2")
    header.add_crs(CRS.from_epsg(25830))
    cloud = laspy.LasData(header)
    cloud.x = np.array([350_000.0, 350_001.0])
    cloud.y = np.array([4_600_000.0, 4_600_001.0])
    cloud.z = np.array([100.0, 101.0])
    cloud.write(path)

    validation = validate_las_laz(path)

    assert validation.point_count == 2
    assert validation.crs == "EPSG:25830"
    assert len(validation.checksum_sha256) == 64


def test_empty_lidar_is_not_accepted(tmp_path: Path) -> None:
    path = tmp_path / "empty.las"
    laspy.LasData(laspy.LasHeader(point_format=3, version="1.2")).write(path)
    with pytest.raises(ValueError, match="no contiene puntos"):
        validate_las_laz(path)


def test_download_manifest_rejects_signed_or_tokenized_urls() -> None:
    with pytest.raises(ValidationError, match="credenciales"):
        DownloadManifest(
            provider="TEST ONLY",
            product_id="test",
            source_uri="https://example.invalid/data?access_token=secret",
            requested_at=datetime(2026, 8, 20, tzinfo=UTC),
            status=AvailabilityState.PROCESSING,
            aoi_hash="a" * 64,
            request_id="test-run",
        )


def test_failed_download_manifest_does_not_invent_checksum_or_size() -> None:
    manifest = DownloadManifest(
        provider="PNOA-CNIG",
        product_id="PNOA-TEST-ONLY.LAZ",
        source_uri="https://example.invalid/public-product-record",
        requested_at=datetime(2026, 8, 20, tzinfo=UTC),
        status=AvailabilityState.ERROR,
        aoi_hash="a" * 64,
        request_id="test-failed-download",
        error_code="PNOA_DOWNLOAD_INCOMPLETE",
    )
    assert manifest.size_bytes is None
    assert manifest.checksum_sha256 is None
