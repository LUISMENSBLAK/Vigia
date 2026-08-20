from __future__ import annotations

import struct
import zlib
from pathlib import Path
from urllib.parse import unquote, urlsplit

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject


def local_raster_path(storage_uri: str, *, storage_root: Path) -> Path:
    parsed = urlsplit(storage_uri)
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        raise ValueError("El producto no está disponible en almacenamiento local.")
    path = Path(unquote(parsed.path)).resolve()
    root = storage_root.resolve()
    if path != root and root not in path.parents:
        raise ValueError("El producto está fuera del almacenamiento geoespacial permitido.")
    if not path.is_file():
        raise ValueError("El producto geoespacial no existe en este nodo.")
    return path


def sample_raster(
    storage_uri: str,
    *,
    longitude: float,
    latitude: float,
    band: int,
    storage_root: Path,
) -> float | None:
    path = local_raster_path(storage_uri, storage_root=storage_root)
    with rasterio.open(path) as dataset:
        if dataset.crs is None or not 1 <= band <= dataset.count:
            raise ValueError("El producto raster no declara CRS/banda válidos.")
        transformer = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
        x, y = transformer.transform(longitude, latitude)
        if not (dataset.bounds.left <= x <= dataset.bounds.right):
            return None
        if not (dataset.bounds.bottom <= y <= dataset.bounds.top):
            return None
        value = next(dataset.sample([(x, y)], indexes=band, masked=True))[0]
        if np.ma.is_masked(value) or not np.isfinite(float(value)):
            return None
        return float(value)


def web_mercator_tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    if z < 0 or not (0 <= x < 2**z and 0 <= y < 2**z):
        raise ValueError("Tesela Web Mercator inválida.")
    extent = 20037508.342789244
    size = 2 * extent / 2**z
    west = -extent + x * size
    east = west + size
    north = extent - y * size
    south = north - size
    return west, south, east, north


def _colorize(values: np.ndarray, *, layer: str) -> np.ndarray:
    rgba = np.zeros((*values.shape, 4), dtype="uint8")
    valid = np.isfinite(values)
    if not valid.any():
        return rgba
    if layer == "NDVI":
        normalized = np.clip((values + 0.2) / 1.0, 0, 1)
        normalized = np.nan_to_num(normalized)
        rgba[..., 0] = (166 * (1 - normalized) + 30 * normalized).astype("uint8")
        rgba[..., 1] = (97 * (1 - normalized) + 125 * normalized).astype("uint8")
        rgba[..., 2] = (58 * (1 - normalized) + 65 * normalized).astype("uint8")
    elif layer in {"NDMI", "NBR"}:
        normalized = np.clip((values + 0.5) / 1.2, 0, 1)
        normalized = np.nan_to_num(normalized)
        rgba[..., 0] = (212 * (1 - normalized) + 32 * normalized).astype("uint8")
        rgba[..., 1] = (126 * (1 - normalized) + 105 * normalized).astype("uint8")
        rgba[..., 2] = (63 * (1 - normalized) + 155 * normalized).astype("uint8")
    elif layer == "SLOPE":
        normalized = np.clip(values / 60, 0, 1)
        normalized = np.nan_to_num(normalized)
        rgba[..., 0] = (245 * (1 - normalized) + 116 * normalized).astype("uint8")
        rgba[..., 1] = (239 * (1 - normalized) + 45 * normalized).astype("uint8")
        rgba[..., 2] = (210 * (1 - normalized) + 29 * normalized).astype("uint8")
    else:
        lower = float(np.nanpercentile(values, 2))
        upper = float(np.nanpercentile(values, 98))
        span = upper - lower if upper > lower else 1.0
        normalized = np.clip((values - lower) / span, 0, 1)
        normalized = np.nan_to_num(normalized)
        shade = (45 + normalized * 185).astype("uint8")
        rgba[..., 0] = shade
        rgba[..., 1] = shade
        rgba[..., 2] = shade
    rgba[..., 3] = np.where(valid, 190, 0).astype("uint8")
    return rgba


def _png_rgba(rgba: np.ndarray) -> bytes:
    if rgba.shape != (256, 256, 4) or rgba.dtype != np.uint8:
        raise ValueError("La imagen de tesela debe ser RGBA 256×256.")

    def chunk(name: bytes, data: bytes) -> bytes:
        body = name + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    scanlines = b"".join(b"\x00" + rgba[row].tobytes() for row in range(256))
    header = struct.pack(">IIBBBBB", 256, 256, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(scanlines, level=6))
        + chunk(b"IEND", b"")
    )


def render_tile(
    storage_uri: str,
    *,
    band: int,
    layer: str,
    z: int,
    x: int,
    y: int,
    storage_root: Path,
) -> bytes:
    path = local_raster_path(storage_uri, storage_root=storage_root)
    destination = np.full((256, 256), np.nan, dtype="float32")
    bounds = web_mercator_tile_bounds(z, x, y)
    with rasterio.open(path) as dataset:
        if dataset.crs is None or not 1 <= band <= dataset.count:
            raise ValueError("El producto raster no declara CRS/banda válidos.")
        reproject(
            source=rasterio.band(dataset, band),
            destination=destination,
            src_transform=dataset.transform,
            src_crs=dataset.crs,
            src_nodata=dataset.nodata,
            dst_transform=from_bounds(*bounds, 256, 256),
            dst_crs="EPSG:3857",
            dst_nodata=np.nan,
            resampling=Resampling.nearest if layer == "ASPECT" else Resampling.bilinear,
        )
    destination[~np.isfinite(destination)] = np.nan
    return _png_rgba(_colorize(destination, layer=layer))
