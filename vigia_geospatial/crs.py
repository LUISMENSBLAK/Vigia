from pyproj import CRS


def require_projected_metric_crs(value: str) -> CRS:
    crs = CRS.from_user_input(value)
    if not crs.is_projected:
        raise ValueError("El análisis de distancias/áreas requiere un CRS proyectado.")
    axis_units = {axis.unit_name.casefold() for axis in crs.axis_info if axis.unit_name}
    if not any(unit in {"metre", "meter"} for unit in axis_units):
        raise ValueError("El CRS de análisis debe utilizar metros.")
    return crs


def etrs89_utm_for_mainland(longitude: float, latitude: float) -> CRS:
    if not (-10 <= longitude <= 4.6 and 35.7 <= latitude <= 44):
        raise ValueError(
            "Fuera del ámbito ETRS89 peninsular/balear; conserva el CRS oficial del producto."
        )
    zone = int((longitude + 180) // 6) + 1
    if zone not in {29, 30, 31}:
        raise ValueError("Huso UTM no admitido para España peninsular/balear.")
    return CRS.from_epsg(25800 + zone)
