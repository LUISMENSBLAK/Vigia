"""National, AOI-driven geospatial foundation for VIGÍA."""

from .aoi import AOIRequest, ResolvedAOI
from .models import AvailabilityState, GeospatialLayer, GeospatialProduct
from .pipeline import RasterCatalogItem, RasterIngestResult, ingest_raster_bytes

__all__ = [
    "AOIRequest",
    "AvailabilityState",
    "GeospatialLayer",
    "GeospatialProduct",
    "RasterCatalogItem",
    "RasterIngestResult",
    "ResolvedAOI",
    "ingest_raster_bytes",
]
