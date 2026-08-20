import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, cast

from pydantic import BaseModel, Field, model_validator
from pyproj import Geod
from shapely.geometry import Polygon, box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity

WGS84_GEOD = Geod(ellps="WGS84")


class AOIRequest(BaseModel):
    bbox: tuple[float, float, float, float] | None = None
    geojson: dict[str, Any] | None = None
    administrative_area: str | None = Field(default=None, min_length=1, max_length=160)
    country: Literal["ES"] | None = None

    @model_validator(mode="after")
    def exactly_one_selector(self) -> "AOIRequest":
        selectors = (self.bbox, self.geojson, self.administrative_area, self.country)
        if sum(item is not None for item in selectors) != 1:
            raise ValueError("La AOI requiere exactamente un selector.")
        if self.bbox is not None:
            west, south, east, north = self.bbox
            if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
                raise ValueError("bbox no válido.")
        return self


@dataclass(frozen=True, slots=True)
class ResolvedAOI:
    geometry: BaseGeometry
    source: str
    reference: str | None = None

    @property
    def geojson(self) -> dict[str, Any]:
        return cast(dict[str, Any], mapping(self.geometry))

    @property
    def hash(self) -> str:
        payload = json.dumps(self.geojson, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    @property
    def area_km2(self) -> float:
        area, _ = WGS84_GEOD.geometry_area_perimeter(self.geometry)
        return abs(area) / 1_000_000


def resolve_inline_aoi(request: AOIRequest, *, max_area_km2: float = 50_000) -> ResolvedAOI:
    if request.bbox is not None:
        geometry: BaseGeometry = box(*request.bbox)
        source = "bbox"
    elif request.geojson is not None:
        geometry = shape(request.geojson)
        source = "geojson"
    else:
        raise ValueError("La AOI administrativa o nacional debe resolverse desde PostGIS.")
    if geometry.is_empty or (
        not isinstance(geometry, Polygon) and geometry.geom_type != "MultiPolygon"
    ):
        raise ValueError("La AOI debe ser Polygon o MultiPolygon.")
    if not geometry.is_valid:
        raise ValueError(f"Geometría AOI inválida: {explain_validity(geometry)}")
    resolved = ResolvedAOI(geometry=geometry, source=source)
    if resolved.area_km2 > max_area_km2:
        raise ValueError("La AOI excede el límite configurado.")
    return resolved
