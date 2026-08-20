from datetime import UTC, datetime, timedelta

from vigia_ai.replay.geospatial import historical_geospatial_context


def test_future_sentinel_and_processing_are_excluded() -> None:
    cutoff = datetime(2020, 8, 1, tzinfo=UTC)
    products = (
        {"layer": "NDMI", "observed_at": cutoff - timedelta(days=2), "available_at": cutoff},
        {"layer": "NDMI", "observed_at": cutoff + timedelta(days=1), "available_at": cutoff},
        {
            "layer": "NDVI",
            "observed_at": cutoff - timedelta(days=1),
            "available_at": cutoff + timedelta(days=1),
        },
    )
    context = historical_geospatial_context(products, as_of=cutoff)
    assert set(context) == {"NDMI"}
    assert context["NDMI"]["observed_at"] < cutoff


def test_static_reference_year_mismatch_is_explicit() -> None:
    cutoff = datetime(2010, 8, 1, tzinfo=UTC)
    context = historical_geospatial_context(
        (
            {
                "layer": "LAND_COVER",
                "observed_at": None,
                "available_at": None,
                "reference_year": 2018,
            },
        ),
        as_of=cutoff,
    )
    assert context["LAND_COVER"]["availability"] == "TEMPORAL_MISMATCH"
