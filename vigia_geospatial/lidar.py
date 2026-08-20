import hashlib
from dataclasses import dataclass
from pathlib import Path

import laspy


@dataclass(frozen=True, slots=True)
class LidarValidation:
    point_count: int
    point_format: int
    version: str
    bounds: tuple[float, float, float, float, float, float]
    crs: str | None
    checksum_sha256: str


def validate_las_laz(path: Path) -> LidarValidation:
    if path.suffix.casefold() not in {".las", ".laz"} or not path.is_file():
        raise ValueError("Se requiere un fichero LAS/LAZ local.")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        with laspy.open(path) as reader:
            header = reader.header
            if header.point_count <= 0:
                raise ValueError("La nube LiDAR no contiene puntos.")
            parsed_crs = header.parse_crs()
            return LidarValidation(
                point_count=header.point_count,
                point_format=header.point_format.id,
                version=str(header.version),
                bounds=(*header.mins, *header.maxs),
                crs=parsed_crs.to_string() if parsed_crs else None,
                checksum_sha256=digest,
            )
    except laspy.errors.LaspyException as exc:
        raise ValueError("Fichero LAS/LAZ corrupto o incompatible.") from exc
