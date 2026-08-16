# Fuentes de datos

| Fuente | Uso previsto | Worker | Estado inicial |
|---|---|---|---|
| NASA FIRMS | Hotspots VIIRS/MODIS NRT | `workers/firms` | Ingestión preparada; sin llamada real |
| AEMET | Observaciones convencionales | `workers/aemet` | Cliente y persistencia preparados; sin llamada real |
| EUMETSAT MTG FCI AFM | Probabilidad/resultado de fuego y calidad | `workers/eumetsat` | Pendiente |
| Copernicus Sentinel | Vegetación, cambios, radar y térmica apropiada | `workers/copernicus` | OAuth/Catalog/índices preparados; sin llamada real |
| PNOA LiDAR/CNIG | Terreno y estructura vegetal derivados | `gis/lidar` | Pendiente |
| EFFIS | Referencia y benchmark externo | Por definir | Pendiente de licencia/alcance |

Cada adaptador debe conservar identificador oficial, versión, licencia, timestamp observado,
timestamp disponible, timestamp recibido, calidad y checksum. “Tiempo real” solo puede usarse si
la latencia medida lo respalda; de lo contrario se muestra `Observado`, `Recibido` y `Latencia`.

Los datos obsoletos no se reutilizan silenciosamente. Una caída produce `SIN_DATOS`, `DEGRADADO`
o `ERROR`, mantiene la edad del último dato y permite continuar con evidencia independiente.

## Licencias y límites verificados documentalmente

- FIRMS sigue la política abierta y de cita de NASA Earthdata. El Area API exige MAP key y publica
  una cuota; VIGÍA distingue cuota, timeout, HTTP y payload inválido.
- AEMET OpenData se registra con licencia CC BY 4.0. Las observaciones actuales han pasado controles
  automáticos; VIGÍA conserva esa cualificación y no las presenta como validadas manualmente.
- Sentinel usa los términos del Copernicus Data Space Ecosystem.
- EUMETSAT remite a su política y licencia de producto. La colección `EO:EUM:DAT:0682` no se
  procesará hasta comprobar acceso, licencia y variables netCDF sobre un producto real.
- PNOA/CNIG usa la licencia oficial compatible con CC BY 4.0 y exige atribución.
