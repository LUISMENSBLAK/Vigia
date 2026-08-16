# VIGÍA

**Sistema español de inteligencia satelital para incendios forestales.**

VIGÍA es una plataforma de investigación geoespacial diseñada para combinar observación
satelital, meteorología, información forestal e inteligencia artificial con trazabilidad e
incertidumbre explícitas. España es el ámbito inicial; Ávila y Castilla y León son las primeras
zonas de investigación de alta resolución. El diseño evita hardcodear una región única y puede
evolucionar hacia cobertura europea.

> Estado: fase 1 ampliada con persistencia y superficies live preparadas. No es un sistema
> operativo de emergencias. No contiene incendios, métricas, riesgo ni predicciones simuladas.
> Sin credenciales y una ejecución remota verificada, todas las fuentes permanecen `SIN_DATOS`.

## Arquitectura

```text
apps/web              Next.js, React, MapLibre GL y Tailwind CSS
services/api          FastAPI, Pydantic y observabilidad estructurada
workers/firms         NASA FIRMS Area CSV, idempotencia, runs y provenance
workers/aemet         AEMET observado, normalización y persistencia separada
workers/copernicus    OAuth2 cacheado, Catalog y requests Sentinel-2 por AOI
database/migrations   PostGIS, esquemas privados, RLS e índices espaciales
vigia_ai              Interfaces científicas por motor (siguientes fases)
gis                    Pipelines raster/LiDAR/terrain (siguientes fases)
docs                   Decisiones auditables y metodología
tests                  API, workers y pruebas científicas deterministas
```

El navegador solo recibe `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`. Las claves secretas y la URL
directa de PostgreSQL son exclusivamente server-side. El frontend no consulta tablas internas:
la API FastAPI es el límite de confianza principal; cualquier superficie Data API futura será
opt-in, con grants mínimos y RLS.

## Requisitos

- Node.js 22 o posterior.
- Python 3.12.
- npm 11 o compatible.
- `uv` para entornos y lockfile Python.
- Docker opcional para PostgreSQL/PostGIS local.

## Instalación local

```bash
cp .env.example .env
npm ci
uv sync --frozen
```

En terminales separadas:

```bash
npm run dev
uv run uvicorn services.api.vigia_api.main:app --reload --port 8000
```

Web: `http://localhost:3000` · API: `http://localhost:8000` · OpenAPI local: `/docs`.

## Variables

`.env.example` contiene todos los nombres sin valores reales. Las integraciones fallan de forma
explícita si falta una variable. Por ejemplo, el worker FIRMS devuelve:

```text
Falta la variable obligatoria NASA_FIRMS_MAP_KEY.
```

Nunca añadas `SUPABASE_SECRET_KEY`, `SUPABASE_DB_URL`, `NASA_FIRMS_MAP_KEY`, `AEMET_API_KEY`,
`COPERNICUS_CLIENT_SECRET` ni `EUMETSAT_CONSUMER_SECRET` a código cliente, logs o commits.

## Supabase y PostGIS

La migración inicial está en `database/migrations/20260816000000_initial_vigia.sql`. Crea PostGIS,
tipos geoespaciales reales, índices GiST, entidades de procedencia y validación, RLS forzado en las
tablas internas, catálogo explícito de fuentes y una vista de salud mediante `security_invoker`.

No se ha aplicado a un proyecto remoto. Antes de hacerlo:

1. revisar la migración en una rama;
2. ejecutar en una base desechable;
3. comprobar geometrías, grants y políticas;
4. ejecutar los advisors de seguridad y rendimiento;
5. aplicar al proyecto elegido y verificar con roles `anon`, `authenticated` y backend.

## NASA FIRMS

`workers/firms/vigia_firms/client.py` implementa el endpoint oficial Area CSV para
`VIIRS_NOAA20_NRT`, `VIIRS_NOAA21_NRT`, `VIIRS_SNPP_NRT` y `MODIS_NRT`. Convierte el tiempo de
adquisición a UTC y conserva fuente, plataforma, instrumento, confianza original, brillo, FRP,
día/noche, payload original y timestamp de recepción. La persistencia registra runs, aplica una
clave determinista, evita duplicados y crea provenance con hashes. No se interpreta cada hotspot
como un incendio independiente; el clustering permanece bloqueado hasta disponer de observaciones
reales verificadas.

Ejecución, únicamente después de aplicar y verificar la base y configurar `.env`:

```bash
uv run python -m workers.firms.vigia_firms
```

## API y mapa

`/v1/fire-observations` devuelve solo filas persistidas como GeoJSON y conserva estado vacío/error.
`/mapa` usa clustering MapLibre y ofrece una lista textual completa. `/v1/status` y `/estado`
obtienen PostGIS, salud de fuentes y última ejecución de workers; una credencial por sí sola nunca
produce `OPERATIVO`.

## Comprobaciones

```bash
npm run typecheck
npm run lint
npm run test
npm run build
uv run ruff check .
uv run mypy
uv run pytest
```

E2E:

```bash
npx playwright install chromium
npm run test:e2e
```

## Documentación

- [Arquitectura](docs/architecture.md)
- [Fuentes](docs/data-sources.md)
- [Metodología de IA](docs/ai-methodology.md)
- [Validación](docs/validation.md)
- [Seguridad](docs/security.md)
- [Cumplimiento europeo](docs/eu-compliance.md)
- [Procedencia](docs/data-provenance.md)
- [Despliegue](docs/deployment.md)
