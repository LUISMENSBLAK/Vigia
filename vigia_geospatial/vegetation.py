from typing import cast

import numpy as np

CLOUD_OR_INVALID_SCL = frozenset({0, 1, 3, 8, 9, 10, 11})


def sentinel2_valid_mask(scl: np.ndarray, data_mask: np.ndarray) -> np.ndarray:
    if scl.shape != data_mask.shape:
        raise ValueError("SCL y dataMask deben compartir dimensiones.")
    mask = (data_mask == 1) & ~np.isin(scl, tuple(CLOUD_OR_INVALID_SCL))
    return cast(np.ndarray, mask)


def normalized_difference(
    left: np.ndarray, right: np.ndarray, valid_mask: np.ndarray
) -> np.ndarray:
    if left.shape != right.shape or left.shape != valid_mask.shape:
        raise ValueError("Bandas y máscara deben compartir dimensiones.")
    left_float = left.astype("float32")
    right_float = right.astype("float32")
    denominator = left_float + right_float
    valid = valid_mask.astype(bool) & np.isfinite(denominator) & (denominator != 0)
    result = np.full(left.shape, np.nan, dtype="float32")
    result[valid] = (left_float[valid] - right_float[valid]) / denominator[valid]
    return result


def sentinel2_indices(
    *,
    red_b04: np.ndarray,
    nir_b08: np.ndarray,
    swir_b11: np.ndarray,
    swir_b12: np.ndarray,
    scl: np.ndarray,
    data_mask: np.ndarray,
) -> dict[str, np.ndarray]:
    valid = sentinel2_valid_mask(scl, data_mask)
    return {
        "ndvi": normalized_difference(nir_b08, red_b04, valid),
        "ndmi": normalized_difference(nir_b08, swir_b11, valid),
        "nbr": normalized_difference(nir_b08, swir_b12, valid),
        "valid_mask": valid,
    }
