from datetime import datetime

from shapely.geometry import Point, shape

from .models import AvailabilityState, GeospatialLayer, GeospatialProduct


def products_for_point(
    products: list[GeospatialProduct],
    *,
    longitude: float,
    latitude: float,
    as_of: datetime,
) -> dict[GeospatialLayer, GeospatialProduct]:
    if as_of.tzinfo is None:
        raise ValueError("as_of debe incluir zona horaria.")
    point = Point(longitude, latitude)
    candidates = [
        product
        for product in products
        if product.availability in {AvailabilityState.AVAILABLE, AvailabilityState.PARTIAL}
        and (product.observed_at is None or product.observed_at <= as_of)
        and (product.processed_at is None or product.processed_at <= as_of)
        and shape(product.footprint_geojson).covers(point)
    ]
    selected: dict[GeospatialLayer, GeospatialProduct] = {}
    minimum = datetime.min.replace(tzinfo=as_of.tzinfo)
    for product in candidates:
        current = selected.get(product.layer)
        if current is None or (product.observed_at or minimum) > (current.observed_at or minimum):
            selected[product.layer] = product
    return selected
