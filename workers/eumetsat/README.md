# EUMETSAT worker

Estado: `EN PREPARACIÓN`. La colección objetivo es MTG FCI Active Fire Monitoring
`EO:EUM:DAT:0682`. EUMETSAT recomienda su cliente oficial EUMDAC y aplica condiciones de licencia
dependientes del producto.

No se han fijado nombres de variables netCDF ni interpretado probabilidad/calidad sin abrir un
producto real y contrastar su metadata. Esa puerta es deliberada: primero se verificará acceso y
licencia; después se conservarán sensing, availability y receipt time, detección, probabilidad si
existe, calidad, coordenadas y latency `received_at - observed_at`.
