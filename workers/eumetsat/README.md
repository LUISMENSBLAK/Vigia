# EUMETSAT worker

Estado: cliente OAuth/Data Store implementado. En la verificación LIVE del `2026-08-20`, OAuth
fue rechazado, mientras que el catálogo anónimo respondió correctamente y devolvió productos
reales de la colección MTG FCI Active Fire Monitoring `EO:EUM:DAT:0682`. Los endpoints siguen el
cliente oficial EUMDAC 3.1.1 y las condiciones de licencia dependen del producto.

No se han fijado nombres de variables netCDF ni interpretado probabilidad/calidad sin abrir un
producto descargado y contrastar su metadata. Esa puerta es deliberada: primero se verificará acceso y
licencia; después se conservarán sensing, availability y receipt time, detección, probabilidad si
existe, calidad, coordenadas y latency `received_at - observed_at`.
