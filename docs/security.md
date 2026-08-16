# Seguridad

- secretos solo server-side y nunca en variables `NEXT_PUBLIC_*`;
- CORS restrictivo y métodos mínimos;
- CSP, `nosniff`, `DENY`, Referrer Policy y Permissions Policy en Next.js;
- validación Pydantic; validación de inputs cliente se añadirá con Zod cuando existan formularios;
- queries parametrizadas mediante SQLAlchemy; no SQL dinámico con entradas;
- logs estructurados con request/ingest/model-run IDs y redacción de secretos;
- dependencias fijadas y lockfiles;
- RLS forzado en tablas internas y sin políticas amplias para `authenticated`;
- vistas API `security_invoker`; ninguna función privilegiada en `public`;
- workers con rol backend de mínimo privilegio.

La migración revoca escrituras a `anon` y `authenticated`. Aplicar la migración no sustituye una
auditoría: antes de producción deben ejecutarse Supabase Database Advisors, análisis de
dependencias, pruebas de roles y revisión de exposición del Data API.
