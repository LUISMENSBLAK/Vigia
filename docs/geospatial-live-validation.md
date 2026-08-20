# Validación geoespacial LIVE — Fase 4B

Fecha de comprobación: 2026-08-20 UTC. Este documento distingue respuesta de servicio, producto
descubierto, descarga validada y artefacto publicado. Un HTTP 200 no implica cobertura científica.

## AOI

La AOI real es la tesela proyectada `[356000, 4501000, 357000, 4502000]` en EPSG:25830, dentro de
la provincia de Ávila. La elección procede de una tesela LiDAR PNOA publicada; no es un límite
administrativo ni una representación de toda Ávila. La configuración incluye España, Castilla y
León, Ávila, municipios asociados y Segovia como segunda provincia de control.

## Fuentes oficiales comprobadas

- IGN OGC API Features: unidades administrativas de comunidad, provincias y municipios. El país
  usa el contorno generalizado GISCO 2024 para evitar una transferencia nacional innecesaria.
- IGN/IDEE WCS MDT: `Elevacion25830_5`, GeoTIFF real, EPSG:25830, 5 m.
- CNIG LiDAR PNOA: catálogo real y tesela `PNOA-2025-CYL-356-4502-H30-NPC01.LAZ`, 5 puntos/m².
  La descarga llegó incompleta en los intentos realizados; validación y publicación `BLOCKED`.
  Tras esos intentos, la configuración de esta ejecución desactiva solo la repetición de la
  transferencia; el materializador nacional mantiene el intento habilitado por defecto.
- Copernicus Data Space: OAuth, catálogo Sentinel-2 L2A y Process API sobre una AOI pequeña.
- IGN/IDEE WFS ocupación del suelo: `lcv:LandCoverUnit`, dataset `siose_ar2017`, nomenclatura
  `CODIIGEValue`; el cliente pagina y conserva geometría/provenance.
- EUMETSAT Data Store: colección `EO:EUM:DAT:0682` y productos AFM visibles por catálogo anónimo.
  Las credenciales adjuntas devolvieron `invalid_client`; descarga/netCDF `BLOCKED`.

## URLs de referencia

- MDT: `https://servicios.idee.es/wcs-inspire/mdt`
- SIOSE AR: `https://servicios.idee.es/wfs-inspire/ocupacion-suelo`
- Administraciones IGN: `https://api-features.ign.es/collections/administrativeunit/items`
- LiDAR CNIG: `https://centrodedescargas.cnig.es/CentroDescargas/catalogo.do?Serie=LIDA3`
- GISCO: `https://gisco-services.ec.europa.eu/distribution/v2/countries/`
- EUMETSAT Data Store guide:
  `https://user.eumetsat.int/resources/user-guides/data-store-detailed-guide`
- EUMETSAT AFM:
  `https://user.eumetsat.int/catalogue/EO%3AEUM%3ADAT%3A0682`

## Estados pendientes

Los Advisors de Security y Performance de Supabase permanecen `NO VERIFICADO`: las variables
locales permiten PostgreSQL/Data API, pero no incluyen un access token de gestión del proyecto.
No se infiere su resultado desde SQL. Los conteos definitivos de productos materializados se
registrarán tras completar la ejecución reproducible del materializador.
