# Scripts

- `apply_migration.py` aplica la migración inicial solo cuando `vigia.sources` no existe; nunca
  reconstruye ni pisa un esquema remoto ya creado.
- `verify_supabase.py` comprueba PostGIS, una operación geoespacial, RLS forzado, la vista pública y
  la denegación de observaciones internas para `anon` y `authenticated`.
- `apply_phase3_migration.py` aplica las tablas internas de fusión, candidatos, contexto térmico e
  historial únicamente cuando la migración inicial existe y Fase 3 todavía no está instalada.
- `apply_phase5_migration.py` aplica una sola vez el contrato del motor nacional de riesgo.
- `verify_phase5.py` comprueba tablas, columnas, constraints, índices, RLS y permisos remotos.
- `run_phase5_risk.py` ejecuta una AOI configurable, impone el contrato temporal y persiste tanto
  resultados numéricos como estados explícitos de datos insuficientes.
- `apply_phase6_migration.py` aplica una sola vez el esquema privado de corpus histórico y Replay,
  únicamente después de verificar que Fase 5 existe.
- `verify_phase6.py` comprueba tablas, índices, RLS, grants e aislamiento del estado LIVE.
- `materialize_phase6_pilot.py` descarga la fuente regional oficial vigente, aplica la política de
  selección congelada, recupera inputs históricos disponibles y ejecuta/persiste un Replay. No
  guarda snapshots brutos ni credenciales en Git.
- `run_phase6_replay.py` ejecuta un caso ya persistido y guarda cada step en un checkpoint local
  atómico bajo `data/cache`; tras una interrupción valida manifest/configuración/commit y reanuda.

Los scripts remotos leen `SUPABASE_DB_URL` desde `.env` sin imprimir la conexión.
Los advisors de Supabase se ejecutan por separado contra el proyecto remoto correcto.

```bash
uv run python -m scripts.apply_migration
uv run python -m scripts.apply_phase3_migration
uv run python -m scripts.apply_phase5_migration
uv run python -m scripts.verify_supabase
uv run python -m scripts.verify_phase5
uv run python -m scripts.apply_phase6_migration
uv run python -m scripts.verify_phase6
uv run python -m scripts.materialize_phase6_pilot --code-commit "$(git rev-parse HEAD)"
uv run python -m scripts.run_phase6_replay --case-id CASE_ID --code-commit "$(git rev-parse HEAD)"
```
