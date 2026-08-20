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

Los scripts remotos leen `SUPABASE_DB_URL` desde `.env` sin imprimir la conexión.
Los advisors de Supabase se ejecutan por separado contra el proyecto remoto correcto.

```bash
uv run python -m scripts.apply_migration
uv run python -m scripts.apply_phase3_migration
uv run python -m scripts.apply_phase5_migration
uv run python -m scripts.verify_supabase
uv run python -m scripts.verify_phase5
```
