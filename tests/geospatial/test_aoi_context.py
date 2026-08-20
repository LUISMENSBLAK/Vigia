from datetime import UTC, datetime, timedelta

import pytest

from vigia_geospatial.aoi import AOIRequest, resolve_inline_aoi
from vigia_geospatial.context import products_for_point
from vigia_geospatial.models import AvailabilityState, GeospatialLayer, GeospatialProduct


def product(product_id: str, observed_at: datetime) -> GeospatialProduct:
    return GeospatialProduct(
        provider="TEST ONLY",
        dataset="SYNTHETIC TEST DATA",
        product_id=product_id,
        layer=GeospatialLayer.NDVI,
        availability=AvailabilityState.AVAILABLE,
        observed_at=observed_at,
        processed_at=observed_at,
        footprint_geojson={
            "type": "Polygon",
            "coordinates": [[[-5, 40], [-4, 40], [-4, 41], [-5, 41], [-5, 40]]],
        },
        source_crs="EPSG:32630",
        output_crs="EPSG:32630",
        source_resolution_m=10,
        output_resolution_m=10,
        configuration_hash="a" * 64,
        software_version="test",
        algorithm="test-only",
        output_hash="b" * 64,
        storage_uri="file:///test-only.tif",
    )


def test_aoi_accepts_bbox_and_geojson_without_region_specific_code() -> None:
    avila = resolve_inline_aoi(AOIRequest(bbox=(-4.9, 40.5, -4.5, 40.8)))
    seville = resolve_inline_aoi(AOIRequest(bbox=(-6.1, 37.2, -5.7, 37.6)))
    polygon = resolve_inline_aoi(AOIRequest(geojson=avila.geojson))

    assert avila.source == "bbox"
    assert seville.hash != avila.hash
    assert polygon.hash == avila.hash
    assert avila.area_km2 > 0


def test_aoi_rejects_multiple_selectors_and_giant_queries() -> None:
    with pytest.raises(ValueError, match="exactamente un selector"):
        AOIRequest(bbox=(-5, 40, -4, 41), administrative_area="Ávila")
    with pytest.raises(ValueError, match="excede"):
        resolve_inline_aoi(AOIRequest(bbox=(-10, 35, 5, 44)), max_area_km2=100)


def test_administrative_and_country_aoi_require_official_postgis_geometry() -> None:
    with pytest.raises(ValueError, match="PostGIS"):
        resolve_inline_aoi(AOIRequest(administrative_area="05"))
    with pytest.raises(ValueError, match="PostGIS"):
        resolve_inline_aoi(AOIRequest(country="ES"))


def test_as_of_excludes_products_observed_or_processed_in_the_future() -> None:
    cutoff = datetime(2026, 8, 20, 12, tzinfo=UTC)
    past = product("past", cutoff - timedelta(days=1))
    future = product("future", cutoff + timedelta(seconds=1))
    late_processing = product("late-processing", cutoff - timedelta(days=2)).model_copy(
        update={"processed_at": cutoff + timedelta(seconds=1)}
    )

    selected = products_for_point(
        [past, future, late_processing], longitude=-4.7, latitude=40.65, as_of=cutoff
    )

    assert selected[GeospatialLayer.NDVI].product_id == "past"
    assert all(item.observed_at is None or item.observed_at <= cutoff for item in selected.values())
    assert all(
        item.processed_at is None or item.processed_at <= cutoff for item in selected.values()
    )


def test_as_of_requires_timezone() -> None:
    with pytest.raises(ValueError, match="zona horaria"):
        products_for_point([], longitude=-4.7, latitude=40.65, as_of=datetime(2026, 8, 20))
