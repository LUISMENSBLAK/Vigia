from datetime import UTC, datetime

import pytest

from workers.firms.vigia_firms.client import (
    FirmsClient,
    FirmsSource,
    MissingFirmsKeyError,
    parse_firms_csv,
)


def test_missing_key_fails_with_exact_variable() -> None:
    with pytest.raises(MissingFirmsKeyError, match="NASA_FIRMS_MAP_KEY"):
        FirmsClient(None)


def test_parses_firms_timestamp_as_utc() -> None:
    payload = (
        "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,bright_ti4,frp,daynight\n"
        "40.6500,-4.7000,2026-08-14,0731,N20,VIIRS,n,331.2,4.8,D\n"
    )
    ingested_at = datetime(2026, 8, 14, 8, 0, tzinfo=UTC)
    rows = parse_firms_csv(payload, FirmsSource.VIIRS_NOAA20_NRT, ingested_at=ingested_at)
    assert len(rows) == 1
    assert rows[0].acquired_at == datetime(2026, 8, 14, 7, 31, tzinfo=UTC)
    assert rows[0].source is FirmsSource.VIIRS_NOAA20_NRT
    assert rows[0].frp == 4.8
