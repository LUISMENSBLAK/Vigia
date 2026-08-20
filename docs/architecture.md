# Arquitectura

## Límites de confianza

El frontend es un consumidor no privilegiado. FastAPI valida entradas, limita CORS, asigna un
`request_id` y será el único componente autorizado a coordinar workers y datos internos. Los
workers escriben mediante credenciales server-side y generan un `ingest_id`. Las tablas viven en
el esquema `vigia`, no expuesto; `api` contiene únicamente superficies explícitas.

## Flujo

1. Un worker obtiene un producto oficial y registra sensing time, availability time y receipt time.
2. El producto se valida y conserva su checksum antes de crear observaciones.
3. El clustering agrupa observaciones, sin identificarlas automáticamente como incendios.
4. Fusion, Detection y Confidence producen resultados versionados y calibrados.
5. Cualquier predicción conserva inputs, configuración, commit, modelo y hashes.
6. La UI presenta procedencia, edad, calidad, incertidumbre y alternativa textual al mapa.

## Tiempo y espacio

Todo timestamp se guarda en `timestamptz` UTC. El frontend podrá mostrar UTC o Europe/Madrid. El
CRS nunca es implícito: geometrías operativas iniciales usan EPSG:4326 y los procesos métricos
deberán reproyectar a un CRS adecuado antes de calcular distancias o áreas.

## Puertas actuales

La base, la persistencia FIRMS/AEMET, el API GeoJSON, el mapa y el health dinámico están preparados
y cubiertos por pruebas sin secretos. Copernicus dispone de autenticación cacheada, Catalog y un
request acotado de índices Sentinel-2. Ninguna de estas piezas equivale a una integración remota
verificada.

El 20 de agosto de 2026 se verificaron PostGIS remoto, tablas, constraints, RLS/grants backend,
persistencia FIRMS/AEMET, OAuth/Catalog/Process de Copernicus y una ejecución real de Fusión. Los
advisors de Supabase no se ejecutaron y permanecen `NO VERIFICADO`. EUMETSAT rechazó OAuth; catálogo,
producto y netCDF siguen `NO VERIFICADO`. Confidence no cruzará su puerta hasta disponer de
evidencia real suficiente y calibración.

## Fase 3: fusión y detección

La cadena ahora separa `ObservationEvidence`, candidato, incidente persistido y recomendación de
estado. Fusion es determinista, configurable y compatible con `as_of`; Detection usa reglas y una
máquina de estados sin confirmación automática. FastAPI expone solo incidentes `public_visible` y
evidencia sanitizada. Las tablas de runs, candidatos y contexto permanecen internas con RLS
forzado. Ver `docs/fusion-engine.md` y `docs/detection-engine.md`.

## Fase 4: base física nacional

`vigia_geospatial` separa catálogo, AOI, almacenamiento, validación raster/COG, terreno, vegetación
y LiDAR. PostGIS guarda footprints, estados, jerarquía administrativa y provenance; los artefactos
se guardan mediante una interfaz local sustituible por object storage. Las consultas por punto y
cobertura aceptan `as_of` y excluyen adquisiciones o procesamientos futuros. Ver
`docs/geospatial-architecture.md`.

## Fase 5: riesgo ambiental nacional

`vigia_ai.risk` permanece separado de detección y spread. `risk_runs` fija AOI, modo,
`as_of`, horizonte, configuración y snapshot; `risk_predictions` conserva índice
experimental, componentes, faltantes, explicación y COG asociado. Los hotspots nunca
son entrada causal del motor de riesgo.
