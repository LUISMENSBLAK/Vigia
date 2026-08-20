from __future__ import annotations

import asyncio
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from xml.etree import ElementTree

import httpx
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry

from .aoi import ResolvedAOI

IGN_ADMIN_API = "https://api-features.ign.es"
IGN_MDT_WCS = "https://servicios.idee.es/wcs-inspire/mdt"
IDEE_LAND_COVER_WFS = "https://servicios.idee.es/wfs-inspire/ocupacion-suelo"
CNIG_DOWNLOADS = "https://centrodedescargas.cnig.es/CentroDescargas"
GISCO_COUNTRIES = (
    "https://gisco-services.ec.europa.eu/distribution/v2/countries/geojson/"
    "CNTR_RG_10M_2024_4326.geojson"
)

GML = "{http://www.opengis.net/gml/3.2}"
LCV = "{http://inspire.ec.europa.eu/schemas/lcv/4.0}"
BASE = "{http://inspire.ec.europa.eu/schemas/base/3.3}"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


class OfficialSourceError(RuntimeError):
    """Sanitized failure returned by an official geospatial source."""


@dataclass(frozen=True, slots=True)
class AdministrativeUnit:
    source_code: str
    external_id: str
    national_code: str
    name: str
    level: str
    geometry_geojson: dict[str, Any]
    source_uri: str
    properties: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CnigLidarItem:
    sequential_id: str
    filename: str
    advertised_size_mb: float | None
    point_density_m2: float | None
    observed_year: int | None
    source_uri: str


@dataclass(frozen=True, slots=True)
class LandCoverFeature:
    external_id: str
    class_uri: str
    class_code: str
    covered_percentage: float | None
    observed_at: datetime | None
    geometry_geojson: dict[str, Any]
    properties: dict[str, Any]


def _multipart(geometry: BaseGeometry) -> MultiPolygon:
    if isinstance(geometry, Polygon):
        return MultiPolygon([geometry])
    if isinstance(geometry, MultiPolygon):
        return geometry
    polygons = [part for part in getattr(geometry, "geoms", ()) if isinstance(part, Polygon)]
    if not polygons:
        raise OfficialSourceError("La fuente oficial no devolvió una geometría poligonal.")
    return MultiPolygon(polygons)


async def fetch_administrative_unit(
    national_code: str,
    *,
    base_url: str = IGN_ADMIN_API,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AdministrativeUnit:
    if not national_code.isdigit() or len(national_code) != 11:
        raise ValueError("El national_code administrativo debe contener 11 dígitos.")
    endpoint = f"{base_url.rstrip('/')}/collections/administrativeunit/items"
    try:
        async with httpx.AsyncClient(timeout=180, transport=transport) as client:
            response = await client.get(
                endpoint,
                params={"f": "json", "nationalcode": national_code, "limit": 2},
                headers={"Accept": "application/geo+json"},
            )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OfficialSourceError("No se pudo consultar la unidad administrativa IGN.") from exc
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list) or len(features) != 1:
        raise OfficialSourceError("IGN no devolvió una unidad administrativa inequívoca.")
    feature = features[0]
    properties = feature.get("properties")
    geometry_payload = feature.get("geometry")
    if not isinstance(properties, dict) or not isinstance(geometry_payload, dict):
        raise OfficialSourceError("La unidad administrativa IGN está incompleta.")
    geometry = _multipart(shape(geometry_payload))
    level_name = str(properties.get("nationallevelname", ""))
    level_map = {
        "País": "COUNTRY",
        "Comunidad autónoma": "AUTONOMOUS_COMMUNITY",
        "Provincia": "PROVINCE",
        "Municipio": "MUNICIPALITY",
    }
    level = level_map.get(level_name)
    if level is None:
        raise OfficialSourceError("IGN devolvió un nivel administrativo no reconocido.")
    return AdministrativeUnit(
        source_code="IGN_ADMINISTRATIVE_UNITS",
        external_id=national_code,
        national_code=national_code,
        name=str(properties.get("nameunit", "")),
        level=level,
        geometry_geojson=dict(mapping(geometry)),
        source_uri=f"{endpoint}?{urlencode({'nationalcode': national_code, 'f': 'json'})}",
        properties=properties,
    )


async def fetch_gisco_country(
    country_code: str,
    *,
    national_code: str,
    endpoint: str = GISCO_COUNTRIES,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AdministrativeUnit:
    if len(country_code) != 2 or not country_code.isalpha():
        raise ValueError("country_code GISCO debe ser ISO alfa-2.")
    try:
        async with httpx.AsyncClient(timeout=180, transport=transport) as client:
            response = await client.get(endpoint, headers={"Accept": "application/geo+json"})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OfficialSourceError("No se pudo consultar el país oficial GISCO.") from exc
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        raise OfficialSourceError("GISCO devolvió un catálogo de países inválido.")
    matches = [
        feature
        for feature in features
        if isinstance(feature, dict)
        and isinstance(feature.get("properties"), dict)
        and feature["properties"].get("CNTR_ID") == country_code.upper()
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("geometry"), dict):
        raise OfficialSourceError("GISCO no devolvió un país inequívoco.")
    feature = matches[0]
    properties = feature["properties"]
    geometry = _multipart(shape(feature["geometry"]))
    return AdministrativeUnit(
        source_code="EUROSTAT_GISCO_COUNTRIES",
        external_id=national_code,
        national_code=national_code,
        name=str(properties.get("CNTR_NAME", country_code.upper())),
        level="COUNTRY",
        geometry_geojson=dict(mapping(geometry)),
        source_uri=endpoint,
        properties=properties,
    )


async def fetch_mdt05(
    *,
    bounds_etrs89_utm30: tuple[float, float, float, float],
    endpoint: str = IGN_MDT_WCS,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[bytes, str]:
    west, south, east, north = bounds_etrs89_utm30
    if not (west < east and south < north):
        raise ValueError("Los límites MDT05 no son válidos.")
    params: list[tuple[str, str | int | float | bool | None]] = [
        ("SERVICE", "WCS"),
        ("REQUEST", "GetCoverage"),
        ("VERSION", "2.0.1"),
        ("COVERAGEID", "Elevacion25830_5"),
        ("SUBSET", f"x({west},{east})"),
        ("SUBSET", f"y({south},{north})"),
        ("FORMAT", "image/tiff"),
    ]
    try:
        async with httpx.AsyncClient(timeout=120, transport=transport) as client:
            response = await client.get(endpoint, params=params, headers={"Accept": "image/tiff"})
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OfficialSourceError("No se pudo descargar la cobertura oficial MDT05.") from exc
    content_type = response.headers.get("content-type", "").split(";", 1)[0]
    if content_type not in {"image/tiff", "image/geotiff"} or not response.content:
        raise OfficialSourceError("MDT05 no devolvió un GeoTIFF verificable.")
    public_uri = f"{endpoint}?{urlencode(params)}"
    return response.content, public_uri


class CnigLidarClient:
    def __init__(
        self,
        *,
        base_url: str = CNIG_DOWNLOADS,
        transport: httpx.AsyncBaseTransport | None = None,
        verify_tls: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._verify_tls = verify_tls

    async def locate(self, *, longitude: float, latitude: float) -> CnigLidarItem:
        coordinates = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                    }
                ],
            },
            separators=(",", ":"),
        )
        params = {"Serie": "LIDA3", "coordenadas": coordinates, "codTipoArchivo": "LAZ"}
        try:
            async with httpx.AsyncClient(
                timeout=120,
                transport=self._transport,
                verify=self._verify_tls,
            ) as client:
                response = await client.get(f"{self._base_url}/catalogo.do", params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OfficialSourceError("No se pudo consultar el catálogo LiDAR PNOA.") from exc
        html = response.text
        filename_match = re.search(r"(PNOA-[^<]+?\.LAZ)", html, re.IGNORECASE)
        sequential_match = re.search(r"linkDescDir_([0-9]+)", html)
        total_match = re.search(r'id="totalArchivos"[^>]+value="([0-9]+)"', html)
        if (
            not filename_match
            or not sequential_match
            or not total_match
            or total_match.group(1) != "1"
        ):
            raise OfficialSourceError("El catálogo PNOA no devolvió una tesela LiDAR inequívoca.")
        row_start = html.rfind("<tr", 0, filename_match.start())
        row_end = html.find("</tr>", filename_match.end())
        if row_start < 0 or row_end < 0:
            raise OfficialSourceError("El catálogo PNOA devolvió una fila incompleta.")
        row = html[row_start:row_end]
        size_match = re.search(r">([0-9]+(?:\.[0-9]+)?)</div>\s*</td>\s*<td", row)
        density_match = re.search(r">([0-9]+(?:\.[0-9]+)?)\s*ptos/m2<", row)
        year_match = re.search(r">(20[0-9]{2})", filename_match.group(1))
        decimal_values = [
            float(value) for value in re.findall(r">([0-9]+[.][0-9]+)</div>", row)
        ]
        advertised_size_mb = (
            decimal_values[-1]
            if decimal_values
            else float(size_match.group(1))
            if size_match
            else None
        )
        filename = filename_match.group(1)
        filename_year = filename[5:9]
        observed_year = (
            int(filename_year)
            if filename_year.isdigit()
            else int(year_match.group(1))
            if year_match
            else None
        )
        source_uri = f"{self._base_url}/detalleArchivo?sec={sequential_match.group(1)}"
        return CnigLidarItem(
            sequential_id=sequential_match.group(1),
            filename=filename,
            advertised_size_mb=advertised_size_mb,
            point_density_m2=float(density_match.group(1)) if density_match else None,
            observed_year=observed_year,
            source_uri=source_uri,
        )

    async def download(self, item: CnigLidarItem) -> bytes:
        try:
            async with httpx.AsyncClient(
                timeout=300,
                transport=self._transport,
                verify=self._verify_tls,
                follow_redirects=True,
            ) as client:
                await client.get(f"{self._base_url}/catalogo.do", params={"Serie": "LIDA3"})
                handoff = await client.post(
                    f"{self._base_url}/descargaDirS3",
                    data={"secuencial": item.sequential_id},
                    headers={"Referer": f"{self._base_url}/catalogo.do?Serie=LIDA3"},
                )
                handoff.raise_for_status()
                signed_match = re.search(
                    r'id="urlPregsigned"\s+value="([^"]+)"', handoff.text
                )
                if not signed_match:
                    raise OfficialSourceError("CNIG no devolvió un enlace temporal de descarga.")
                signed_url = html.unescape(signed_match.group(1))
                parsed_signed = httpx.URL(signed_url)
                if (
                    parsed_signed.scheme != "https"
                    or parsed_signed.host is None
                    or not parsed_signed.host.endswith(".amazonaws.com")
                ):
                    raise OfficialSourceError("CNIG devolvió un destino de descarga no permitido.")
                response = await client.get(signed_url)
                if response.status_code == 404:
                    response = await client.post(
                        f"{self._base_url}/descargaDir",
                        data={"secDescDirLA": item.sequential_id},
                        headers={"Referer": f"{self._base_url}/catalogo.do?Serie=LIDA3"},
                    )
                response.raise_for_status()
        except httpx.HTTPError:
            raise OfficialSourceError("No se pudo descargar la tesela LiDAR PNOA.") from None
        if not response.content.startswith(b"LASF"):
            raise OfficialSourceError("PNOA no devolvió un fichero LAS/LAZ válido.")
        return response.content


def _coordinates(pos_list: str) -> list[tuple[float, float]]:
    values = [float(value) for value in pos_list.split()]
    if len(values) < 8 or len(values) % 2:
        raise OfficialSourceError("SIOSE devolvió coordenadas GML inválidas.")
    return list(zip(values[0::2], values[1::2], strict=True))


def _surface_geometry(element: ElementTree.Element) -> MultiPolygon:
    polygons: list[Polygon] = []
    for patch in element.findall(f".//{GML}PolygonPatch"):
        exterior_node = patch.find(f"./{GML}exterior/{GML}LinearRing/{GML}posList")
        if exterior_node is None or exterior_node.text is None:
            continue
        interiors = []
        for interior in patch.findall(f"./{GML}interior/{GML}LinearRing/{GML}posList"):
            if interior.text:
                interiors.append(_coordinates(interior.text))
        polygon = Polygon(_coordinates(exterior_node.text), interiors)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if isinstance(polygon, Polygon) and not polygon.is_empty:
            polygons.append(polygon)
        elif isinstance(polygon, MultiPolygon):
            polygons.extend(polygon.geoms)
    if not polygons:
        raise OfficialSourceError("SIOSE devolvió una unidad sin superficie GML.")
    return MultiPolygon(polygons)


def _safe_xml(content: bytes) -> ElementTree.Element:
    if len(content) > 25_000_000:
        raise OfficialSourceError("La respuesta XML excede el límite configurado.")
    preamble = content[:4096].upper()
    if b"<!DOCTYPE" in preamble or b"<!ENTITY" in preamble:
        raise OfficialSourceError("La respuesta XML contiene declaraciones no permitidas.")
    try:
        return ElementTree.fromstring(content)  # noqa: S314
    except ElementTree.ParseError as exc:
        raise OfficialSourceError("SIOSE devolvió GML incompleto o inválido.") from exc


def parse_land_cover_gml(content: bytes, *, clip: BaseGeometry) -> list[LandCoverFeature]:
    root = _safe_xml(content)
    output: list[LandCoverFeature] = []
    for unit in root.findall(f".//{LCV}LandCoverUnit"):
        local_id = unit.findtext(f".//{BASE}localId")
        class_node = unit.find(f".//{LCV}LandCoverObservation/{LCV}class")
        geometry_node = unit.find(f"./{LCV}geometry")
        if local_id is None or class_node is None or geometry_node is None:
            continue
        class_uri = class_node.attrib.get(XLINK_HREF)
        if not class_uri:
            continue
        geometry = _surface_geometry(geometry_node).intersection(clip)
        if geometry.is_empty:
            continue
        geometry = _multipart(geometry)
        percentage_text = unit.findtext(f".//{LCV}coveredPercentage")
        observed_text = unit.findtext(f".//{LCV}observationDate")
        observed_at = None
        if observed_text:
            observed_at = datetime.fromisoformat(observed_text.replace("Z", "+00:00"))
        output.append(
            LandCoverFeature(
                external_id=local_id,
                class_uri=class_uri,
                class_code=class_uri.rstrip("/").rsplit("/", 1)[-1],
                covered_percentage=float(percentage_text) if percentage_text else None,
                observed_at=observed_at,
                geometry_geojson=dict(mapping(geometry)),
                properties={"namespace": "ES.SCNE.CLC", "dataset": "siose_ar2017"},
            )
        )
    return output


async def fetch_land_cover(
    aoi: ResolvedAOI,
    *,
    endpoint: str = IDEE_LAND_COVER_WFS,
    page_size: int = 100,
    concurrency: int = 6,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[list[LandCoverFeature], list[bytes], str]:
    if not 1 <= page_size <= 1000:
        raise ValueError("page_size debe estar entre 1 y 1000.")
    west, south, east, north = aoi.geometry.bounds
    base_params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": "lcv:LandCoverUnit",
        "SRSNAME": "EPSG:4326",
        "BBOX": f"{west},{south},{east},{north},EPSG:4326",
    }
    try:
        async with httpx.AsyncClient(timeout=120, transport=transport) as client:
            hits = await client.get(endpoint, params={**base_params, "RESULTTYPE": "hits"})
        hits.raise_for_status()
        root = _safe_xml(hits.content)
        matched = int(root.attrib.get("numberMatched", "0"))
    except (httpx.HTTPError, ElementTree.ParseError, ValueError) as exc:
        raise OfficialSourceError("No se pudo consultar la cobertura SIOSE AR.") from exc
    if matched == 0:
        return [], [], f"{endpoint}?{urlencode(base_params)}"
    semaphore = asyncio.Semaphore(concurrency)

    async def fetch_page(start_index: int) -> bytes:
        async with semaphore:
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    async with httpx.AsyncClient(timeout=180, transport=transport) as client:
                        response = await client.get(
                            endpoint,
                            params={
                                **base_params,
                                "COUNT": page_size,
                                "STARTINDEX": start_index,
                            },
                        )
                    response.raise_for_status()
                    _safe_xml(response.content)
                    return response.content
                except (httpx.HTTPError, ElementTree.ParseError, OfficialSourceError) as exc:
                    last_error = exc
                    if attempt < 2:
                        await asyncio.sleep(0.5 * (attempt + 1))
            raise OfficialSourceError("Una página SIOSE AR no pudo validarse.") from last_error

    pages = await asyncio.gather(*(fetch_page(index) for index in range(0, matched, page_size)))
    features_by_id: dict[str, LandCoverFeature] = {}
    for page in pages:
        for feature in parse_land_cover_gml(page, clip=aoi.geometry):
            features_by_id[feature.external_id] = feature
    return list(features_by_id.values()), pages, f"{endpoint}?{urlencode(base_params)}"


def write_download(path: Path, content: bytes) -> None:
    """Write an already validated download atomically; no credentials are accepted here."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(content)
    temporary.replace(path)
