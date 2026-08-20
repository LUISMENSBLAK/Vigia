from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import laspy
import numpy as np
import rasterio
from rasterio.transform import from_origin

from .raster import RasterValidation, create_cog, derive_terrain

FLOAT_NODATA = -9999.0


@dataclass(frozen=True, slots=True)
class DerivedRaster:
    layer: str
    content: bytes
    validation: RasterValidation
    units: str
    algorithm: str
    quality: dict[str, Any]


def array_to_cog(
    array: np.ndarray,
    *,
    transform: rasterio.Affine,
    crs: str,
    layer: str,
    units: str,
    algorithm: str,
    quality: dict[str, Any] | None = None,
    resampling: str = "average",
) -> DerivedRaster:
    if array.ndim != 2 or array.size == 0:
        raise ValueError("La capa derivada debe ser una matriz 2D no vacía.")
    output = np.where(np.isfinite(array), array, FLOAT_NODATA).astype("float32")
    with TemporaryDirectory(prefix="vigia-derived-") as directory:
        source = Path(directory) / "source.tif"
        destination = Path(directory) / "output.cog.tif"
        with rasterio.open(
            source,
            "w",
            driver="GTiff",
            width=output.shape[1],
            height=output.shape[0],
            count=1,
            dtype="float32",
            crs=crs,
            transform=transform,
            nodata=FLOAT_NODATA,
        ) as dataset:
            dataset.write(output, 1)
            dataset.set_band_description(1, layer)
            dataset.update_tags(1, units=units, algorithm=algorithm)
        validation = create_cog(source, destination, resampling=resampling)
        content = destination.read_bytes()
    valid_count = int(np.isfinite(array).sum())
    return DerivedRaster(
        layer=layer,
        content=content,
        validation=validation,
        units=units,
        algorithm=algorithm,
        quality={
            **(quality or {}),
            "valid_pixels": valid_count,
            "total_pixels": int(array.size),
            "valid_fraction": valid_count / int(array.size),
        },
    )


def derive_terrain_cogs(source: Path) -> list[DerivedRaster]:
    with rasterio.open(source) as dataset:
        if dataset.count != 1 or dataset.crs is None:
            raise ValueError("MDT05 debe contener una banda y CRS.")
        elevation = dataset.read(1).astype("float64")
        mask = dataset.read_masks(1) == 0
        if dataset.nodata is not None:
            mask |= elevation == dataset.nodata
        elevation[mask] = np.nan
        terrain = derive_terrain(
            elevation,
            resolution_x_m=abs(dataset.res[0]),
            resolution_y_m=abs(dataset.res[1]),
            nodata_mask=mask,
        )
        common = {
            "transform": dataset.transform,
            "crs": dataset.crs.to_string(),
            "quality": {"source": "IGN_MDT05", "nodata_preserved": True},
        }
        return [
            array_to_cog(
                elevation,
                layer="ELEVATION",
                units="m",
                algorithm="identity_from_ign_mdt05",
                **common,
            ),
            array_to_cog(
                terrain["slope_degrees"],
                layer="SLOPE",
                units="degree",
                algorithm="numpy_gradient_horn_equivalent_v1",
                **common,
            ),
            array_to_cog(
                terrain["aspect_degrees"],
                layer="ASPECT",
                units="degree_clockwise_from_north",
                algorithm="numpy_gradient_aspect_v1",
                resampling="nearest",
                **common,
            ),
            array_to_cog(
                terrain["ruggedness_m"],
                layer="TERRAIN_RUGGEDNESS",
                units="m",
                algorithm="mean_absolute_eight_neighbor_difference_v1",
                **common,
            ),
        ]


def split_sentinel_index_cogs(source: Path) -> list[DerivedRaster]:
    with rasterio.open(source) as dataset:
        if dataset.count != 4 or dataset.crs is None:
            raise ValueError("El producto Sentinel-2 debe contener NDVI, NDMI, NBR y máscara.")
        valid_mask = dataset.read(4) == 1
        common = {
            "transform": dataset.transform,
            "crs": dataset.crs.to_string(),
            "quality": {
                "cloud_mask": "SCL",
                "invalid_scl_classes": [0, 1, 3, 8, 9, 10, 11],
                "data_mask_required": True,
            },
        }
        output = []
        for band, layer in enumerate(("NDVI", "NDMI", "NBR"), 1):
            values = dataset.read(band).astype("float32")
            values[~valid_mask] = np.nan
            output.append(
                array_to_cog(
                    values,
                    layer=layer,
                    units="unitless",
                    algorithm=f"sentinel2_{layer.casefold()}_scl_masked_v1",
                    **common,
                )
            )
        return output


def _grid_indices(
    x: np.ndarray,
    y: np.ndarray,
    *,
    min_x: float,
    max_y: float,
    resolution_m: float,
    width: int,
    height: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    columns = np.floor((x - min_x) / resolution_m).astype("int64")
    rows = np.floor((max_y - y) / resolution_m).astype("int64")
    valid = (columns >= 0) & (columns < width) & (rows >= 0) & (rows < height)
    return rows, columns, valid


def _mean_grid(
    rows: np.ndarray,
    columns: np.ndarray,
    values: np.ndarray,
    valid: np.ndarray,
    shape: tuple[int, int],
) -> np.ndarray:
    flat = rows[valid] * shape[1] + columns[valid]
    sums = np.bincount(flat, weights=values[valid], minlength=shape[0] * shape[1])
    counts = np.bincount(flat, minlength=shape[0] * shape[1])
    result = np.full(shape[0] * shape[1], np.nan, dtype="float64")
    populated = counts > 0
    result[populated] = sums[populated] / counts[populated]
    return result.reshape(shape)


def _max_grid(
    rows: np.ndarray,
    columns: np.ndarray,
    values: np.ndarray,
    valid: np.ndarray,
    shape: tuple[int, int],
) -> np.ndarray:
    flat = rows[valid] * shape[1] + columns[valid]
    result = np.full(shape[0] * shape[1], -np.inf, dtype="float64")
    np.maximum.at(result, flat, values[valid])
    result[~np.isfinite(result)] = np.nan
    return result.reshape(shape)


def derive_lidar_cogs(source: Path, *, resolution_m: float = 5.0) -> list[DerivedRaster]:
    if resolution_m <= 0:
        raise ValueError("La resolución LiDAR debe ser positiva.")
    with laspy.open(source) as reader:
        header = reader.header
        parsed_crs = header.parse_crs()
        if parsed_crs is None:
            raise ValueError("La tesela LiDAR no declara CRS.")
        try:
            points = reader.read()
        except Exception:
            raise ValueError("No se pudo descomprimir íntegramente la tesela LiDAR.") from None
    min_x, min_y, _ = header.mins
    max_x, max_y, _ = header.maxs
    width = int(np.ceil((max_x - min_x) / resolution_m))
    height = int(np.ceil((max_y - min_y) / resolution_m))
    if width <= 0 or height <= 0 or width * height > 4_000_000:
        raise ValueError("La malla LiDAR solicitada excede el límite de seguridad.")
    shape = (height, width)
    rows, columns, inside = _grid_indices(
        np.asarray(points.x),
        np.asarray(points.y),
        min_x=min_x,
        max_y=max_y,
        resolution_m=resolution_m,
        width=width,
        height=height,
    )
    classification = np.asarray(points.classification)
    ground = inside & (classification == 2)
    first_return = inside & (np.asarray(points.return_number) == 1)
    vegetation = inside & np.isin(classification, (3, 4, 5))
    z = np.asarray(points.z)
    dtm = _mean_grid(rows, columns, z, ground, shape)
    dsm = _max_grid(rows, columns, z, first_return, shape)
    vegetation_surface = _max_grid(rows, columns, z, vegetation, shape)
    canopy_height = vegetation_surface - dtm
    canopy_height[(canopy_height < 0) | ~np.isfinite(canopy_height)] = np.nan
    transform = from_origin(min_x, max_y, resolution_m, resolution_m)
    common = {
        "transform": transform,
        "crs": parsed_crs.to_string(),
        "quality": {
            "classification_ground": [2],
            "classification_vegetation": [3, 4, 5],
            "no_spatial_interpolation": True,
            "point_count": int(header.point_count),
        },
    }
    return [
        array_to_cog(
            dtm,
            layer="LIDAR_DTM",
            units="m",
            algorithm="mean_ground_classification_per_cell_v1",
            **common,
        ),
        array_to_cog(
            dsm,
            layer="LIDAR_DSM",
            units="m",
            algorithm="maximum_first_return_per_cell_v1",
            **common,
        ),
        array_to_cog(
            canopy_height,
            layer="CANOPY_HEIGHT",
            units="m",
            algorithm="max_vegetation_return_minus_ground_mean_per_cell_v1",
            **common,
        ),
    ]
