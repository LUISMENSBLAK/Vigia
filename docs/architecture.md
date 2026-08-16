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

La aplicación remota de PostGIS, los tests de roles, advisors, FIRMS LIVE y la primera persistencia
permanecen bloqueados por ausencia del proyecto/credenciales VIGÍA. EUMETSAT netCDF, clustering y
Confidence no cruzarán su puerta hasta disponer de evidencia real suficiente.
