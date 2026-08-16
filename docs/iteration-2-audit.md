# Auditoría de continuación — 2026-08-16

## Punto de partida

- PR auditado: `#1 Build VIGÍA phase 1 foundation`, draft.
- Rama: `agent/phase-1-foundation`.
- Commit remoto auditado: `508dd9da88568064430c57f3f2747fe4e55ad89f`.
- `main` no se modificó y no se realizó merge.
- La copia local se alineó con el commit remoto después de comprobar que ambos árboles eran
  idénticos.

## Verificación previa a cambios

| Comprobación | Resultado observado |
|---|---|
| TypeScript | GREEN |
| ESLint | GREEN |
| Vitest | GREEN, 1 test |
| Next.js build | GREEN, 16 rutas |
| Ruff | GREEN |
| mypy strict | GREEN |
| pytest | GREEN, 5 tests |
| Playwright | NO EJECUTADO; Chromium no disponible |

## Hallazgos de base y seguridad

- La migración existente ya contenía los esquemas `vigia` y `api`, PostGIS, pgcrypto, todas las
  entidades requeridas, geometrías EPSG:4326, índices GiST, RLS forzado y vista
  `security_invoker`. Se corrigió en lugar de crear una segunda migración equivalente.
- Se añadieron índices de claves foráneas que faltaban, constraints temporales/físicos, catálogo de
  fuentes y claves idempotentes no nulas para observaciones.
- `anon` y `authenticated` solo reciben lecturas explícitas de catálogo/health y ninguna escritura.
  El frontend no recibe `SUPABASE_SECRET_KEY` ni `SUPABASE_DB_URL`.
- `.env` continúa ignorado y estaba ausente durante esta auditoría. `.env.example` no contiene
  secretos.

## Infraestructura remota

Estado: `SIN_DATOS`.

No había un proyecto Supabase identificable como VIGÍA ni `SUPABASE_DB_URL` local. No se tocó ningún
proyecto no relacionado. Por tanto, no se ejecutaron ni se declaran aprobados:

- aplicación remota de migración;
- query PostGIS remota;
- pruebas reales `anon`, `authenticated` y backend;
- Security Advisor;
- Performance Advisor.

Los comandos preparados son:

```bash
uv run python -m scripts.apply_migration
uv run python -m scripts.verify_supabase
```

## Integraciones externas

| Fuente | Implementación | Comprobación real |
|---|---|---|
| NASA FIRMS | Fetch, timeout/HTTP/cuota, CSV, UTC, raw, runs, idempotencia, DB, provenance | NO; falta `NASA_FIRMS_MAP_KEY` y DB |
| AEMET | Flujo de dos peticiones, observado, normalización, DB, provenance | NO; falta `AEMET_API_KEY` y DB |
| Copernicus | OAuth2 cacheado, Catalog, AOI Sentinel-2 NDVI/NDMI/NBR | NO; faltan credenciales |
| EUMETSAT MTG-FCI | Contrato y colección documentados | NO; parsing netCDF bloqueado hasta producto/licencia real |

Ninguna fuente se marca `OPERATIVO` por la mera presencia de una clave. FIRMS conserva hotspots como
observaciones; no crea incidentes. Clustering y Confidence permanecen sin ejecución hasta existir
datos reales verificables.

## Superficies de producto

- `/v1/fire-observations` devuelve únicamente observaciones persistidas o un estado vacío/error
  explícito.
- `/mapa` incorpora clustering sobrio, selección y alternativa textual completa.
- `/v1/status` consulta PostGIS, source health y última ejecución de workers cuando existe DB.
- `/estado` representa dinámicamente comprobación, observación, recepción, latencia y error.

## Puerta pendiente para PR #1

El PR no está listo para merge según el criterio acordado hasta completar Supabase remoto, advisors,
una llamada FIRMS real, persistencia real y consumo real por API/mapa. Playwright tampoco puede
figurar como aprobado hasta ejecutarse con Chromium.
