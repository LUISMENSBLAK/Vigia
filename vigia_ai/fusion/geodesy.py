import math

EARTH_MEAN_RADIUS_M = 6_371_008.8


def geodesic_distance_m(
    left: tuple[float, float], right: tuple[float, float]
) -> float:
    """Return great-circle distance for (longitude, latitude) WGS84 points."""
    left_lon, left_lat = map(math.radians, left)
    right_lon, right_lat = map(math.radians, right)
    delta_lon = right_lon - left_lon
    delta_lat = right_lat - left_lat
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(left_lat) * math.cos(right_lat) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_MEAN_RADIUS_M * math.asin(min(1.0, math.sqrt(haversine)))


def centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    if not points:
        raise ValueError("Se requiere al menos un punto.")
    vectors = []
    for longitude, latitude in points:
        lon_rad = math.radians(longitude)
        lat_rad = math.radians(latitude)
        vectors.append(
            (
                math.cos(lat_rad) * math.cos(lon_rad),
                math.cos(lat_rad) * math.sin(lon_rad),
                math.sin(lat_rad),
            )
        )
    x = sum(vector[0] for vector in vectors) / len(vectors)
    y = sum(vector[1] for vector in vectors) / len(vectors)
    z = sum(vector[2] for vector in vectors) / len(vectors)
    return (
        math.degrees(math.atan2(y, x)),
        math.degrees(math.atan2(z, math.sqrt(x * x + y * y))),
    )
