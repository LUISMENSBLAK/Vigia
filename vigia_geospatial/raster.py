import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.shutil import copy as raster_copy

from .crs import require_projected_metric_crs


@dataclass(frozen=True, slots=True)
class RasterValidation:
    width: int
    height: int
    bands: int
    crs: str
    resolution: tuple[float, float]
    bounds: tuple[float, float, float, float]
    nodata: float | int | None
    tiled: bool
    overviews: tuple[int, ...]
    checksum_sha256: str
    is_cog: bool


def validate_raster(path: Path, *, require_cog: bool = False) -> RasterValidation:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Raster ausente o vacío.")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        with rasterio.open(path) as dataset:
            if dataset.width <= 0 or dataset.height <= 0 or dataset.count <= 0:
                raise ValueError("Dimensiones raster no válidas.")
            if dataset.crs is None:
                raise ValueError("Raster sin CRS.")
            if dataset.transform.is_identity:
                raise ValueError("Raster sin georreferenciación válida.")
            resolution = (abs(dataset.res[0]), abs(dataset.res[1]))
            if min(resolution) <= 0:
                raise ValueError("Resolución raster no válida.")
            overviews = tuple(dataset.overviews(1))
            tiled = bool(dataset.profile.get("tiled", False))
            is_cog = (
                dataset.driver == "GTiff"
                and tiled
                and (bool(overviews) or max(dataset.width, dataset.height) <= 512)
            )
            if require_cog and not is_cog:
                raise ValueError("El raster no cumple la estructura COG mínima.")
            return RasterValidation(
                width=dataset.width,
                height=dataset.height,
                bands=dataset.count,
                crs=dataset.crs.to_string(),
                resolution=resolution,
                bounds=tuple(dataset.bounds),
                nodata=dataset.nodata,
                tiled=tiled,
                overviews=overviews,
                checksum_sha256=digest,
                is_cog=is_cog,
            )
    except rasterio.errors.RasterioError as exc:
        raise ValueError("Formato raster corrupto o no compatible.") from exc


def create_cog(source: Path, destination: Path, *, resampling: str = "average") -> RasterValidation:
    destination.parent.mkdir(parents=True, exist_ok=True)
    raster_copy(
        source,
        destination,
        driver="COG",
        compress="DEFLATE",
        blocksize=512,
        overview_resampling=resampling,
    )
    return validate_raster(destination, require_cog=True)


def derive_terrain(
    elevation: np.ndarray,
    *,
    resolution_x_m: float,
    resolution_y_m: float,
    nodata_mask: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    if elevation.ndim != 2 or min(elevation.shape) < 3:
        raise ValueError("El MDT debe ser una matriz 2D de al menos 3×3.")
    if resolution_x_m <= 0 or resolution_y_m <= 0:
        raise ValueError("La resolución debe ser positiva y expresarse en metros.")
    surface = elevation.astype("float64", copy=True)
    mask = np.isnan(surface) if nodata_mask is None else nodata_mask.astype(bool)
    surface[mask] = np.nan
    gradient_y, gradient_x = np.gradient(surface, resolution_y_m, resolution_x_m)
    slope = np.degrees(np.arctan(np.hypot(gradient_x, gradient_y)))
    aspect = (np.degrees(np.arctan2(-gradient_x, gradient_y)) + 360) % 360
    padded = np.pad(surface, 1, mode="edge")
    differences = []
    for row_offset in range(3):
        for column_offset in range(3):
            if row_offset == 1 and column_offset == 1:
                continue
            neighbor = padded[
                row_offset : row_offset + surface.shape[0],
                column_offset : column_offset + surface.shape[1],
            ]
            differences.append(np.abs(neighbor - surface))
    difference_stack = np.stack(differences)
    valid_neighbor_count = np.sum(np.isfinite(difference_stack), axis=0)
    ruggedness = np.divide(
        np.nansum(difference_stack, axis=0),
        valid_neighbor_count,
        out=np.full(surface.shape, np.nan),
        where=valid_neighbor_count > 0,
    )
    for layer in (slope, aspect, ruggedness):
        layer[mask] = np.nan
    return {"slope_degrees": slope, "aspect_degrees": aspect, "ruggedness_m": ruggedness}


def validate_metric_raster_crs(path: Path) -> str:
    with rasterio.open(path) as dataset:
        if dataset.crs is None:
            raise ValueError("Raster sin CRS.")
        return require_projected_metric_crs(dataset.crs.to_string()).to_string()
