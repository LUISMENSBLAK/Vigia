# Despliegue

## Entornos

Development, staging y production deben usar proyectos y credenciales separados. Los mocks solo se
permiten con `VIGIA_ENABLE_LIVE_DATA=false`, en un entorno separado y con la etiqueta visible
`DATOS DE DEMOSTRACIÓN`.

## Web

Construir con `npm ci && npm run build`. Configurar únicamente URL pública, URL de API, URL de
Supabase y publishable key. Mantener los headers de seguridad y revisar CSP al añadir proveedores.

## API y workers

Construir la imagen con el lockfile Python. Las credenciales entran desde el gestor de secretos del
entorno. Health checks no confunden proceso vivo con fuentes operativas: `/health` verifica la API;
`/v1/status` informa cada dependencia.

## Base de datos

Aplicar migraciones primero en staging, ejecutar advisors y pruebas de roles, comprobar PostGIS y
backup, y solo entonces promover la misma migración inmutable. Una migración no verificada nunca
debe hacer que la UI marque la base como operativa.
