# Fuentes de datos

| Fuente | Uso previsto | Worker | Estado inicial |
|---|---|---|---|
| NASA FIRMS | Hotspots VIIRS/MODIS NRT | `workers/firms` | Cliente implementado; sin ingestión |
| AEMET | Observaciones y predicciones meteorológicas | `workers/aemet` | Pendiente |
| EUMETSAT MTG FCI AFM | Probabilidad/resultado de fuego y calidad | `workers/eumetsat` | Pendiente |
| Copernicus Sentinel | Vegetación, cambios, radar y térmica apropiada | `workers/copernicus` | Pendiente |
| PNOA LiDAR/CNIG | Terreno y estructura vegetal derivados | `gis/lidar` | Pendiente |
| EFFIS | Referencia y benchmark externo | Por definir | Pendiente de licencia/alcance |

Cada adaptador debe conservar identificador oficial, versión, licencia, timestamp observado,
timestamp disponible, timestamp recibido, calidad y checksum. “Tiempo real” solo puede usarse si
la latencia medida lo respalda; de lo contrario se muestra `Observado`, `Recibido` y `Latencia`.

Los datos obsoletos no se reutilizan silenciosamente. Una caída produce `SIN_DATOS`, `DEGRADADO`
o `ERROR`, mantiene la edad del último dato y permite continuar con evidencia independiente.
