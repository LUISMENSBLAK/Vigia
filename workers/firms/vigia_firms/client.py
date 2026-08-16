import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

import httpx


class FirmsSource(StrEnum):
    VIIRS_NOAA20_NRT = "VIIRS_NOAA20_NRT"
    VIIRS_NOAA21_NRT = "VIIRS_NOAA21_NRT"
    VIIRS_SNPP_NRT = "VIIRS_SNPP_NRT"
    MODIS_NRT = "MODIS_NRT"


class MissingFirmsKeyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FirmsObservation:
    latitude: float
    longitude: float
    acquired_at: datetime
    satellite: str
    instrument: str
    confidence: str | None
    brightness: float | None
    frp: float | None
    daynight: str | None
    source: FirmsSource
    ingested_at: datetime


def _number(row: dict[str, str], key: str) -> float | None:
    value = row.get(key, "").strip()
    return float(value) if value else None


def parse_firms_csv(
    payload: str,
    source: FirmsSource,
    *,
    ingested_at: datetime,
) -> list[FirmsObservation]:
    observations: list[FirmsObservation] = []
    for row in csv.DictReader(io.StringIO(payload)):
        acquisition = datetime.strptime(
            f"{row['acq_date']} {row['acq_time'].zfill(4)}", "%Y-%m-%d %H%M"
        ).replace(tzinfo=UTC)
        observations.append(
            FirmsObservation(
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                acquired_at=acquisition,
                satellite=row.get("satellite", ""),
                instrument=row.get("instrument", ""),
                confidence=row.get("confidence") or None,
                brightness=_number(row, "bright_ti4") or _number(row, "brightness"),
                frp=_number(row, "frp"),
                daynight=row.get("daynight") or None,
                source=source,
                ingested_at=ingested_at,
            )
        )
    return observations


class FirmsClient:
    base_url = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

    def __init__(self, map_key: str | None, *, timeout_seconds: float = 30.0) -> None:
        if not map_key:
            raise MissingFirmsKeyError("Falta la variable obligatoria NASA_FIRMS_MAP_KEY.")
        self._map_key = map_key
        self._timeout = timeout_seconds

    async def fetch_area(
        self,
        source: FirmsSource,
        *,
        bbox: tuple[float, float, float, float] = (-9.5, 35.7, 4.6, 43.9),
        day_range: int = 1,
        end_date: date | None = None,
    ) -> list[FirmsObservation]:
        if day_range not in range(1, 6):
            raise ValueError("day_range debe estar entre 1 y 5.")
        area = ",".join(str(value) for value in bbox)
        target_date = (end_date or datetime.now(UTC).date()).isoformat()
        url = f"{self.base_url}/{self._map_key}/{source.value}/{area}/{day_range}/{target_date}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(url, headers={"Accept": "text/csv"})
            response.raise_for_status()
        return parse_firms_csv(response.text, source, ingested_at=datetime.now(UTC))
