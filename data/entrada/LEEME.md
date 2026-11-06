# Carga manual de alertas de deforestación (Geobosques)

Geobosques (PNCB – MINAM) bloquea las descargas automáticas desde fuera del Perú.
Para actualizar el módulo de deforestación (recomendado: una vez al mes):

1. Entra a https://geobosques.minam.gob.pe/geobosque/view/descargas.php
2. Categoría **ALERTA TEMPRANA DE DEFORESTACIÓN (ATD)** → descarga **"Alertas Tempranas 2026 – PNCB (Puntos)"**.
   El archivo se llama `Alertas_PNCB_shape_2026.zip` (unos 13 MB). No lo descomprimas.
3. En GitHub, abre esta carpeta (`data/entrada`) → **Add file → Upload files** → arrastra el zip → **Commit changes**.
   Si ya existe un zip del mismo año, súbelo igual: GitHub lo reemplaza.

La plataforma lo procesa sola en unos minutos (cruce con ANP y zonas de amortiguamiento) y publica los resultados.

# Focos de calor 2020–hoy sin MAP_KEY (descarga de archivo de NASA FIRMS)

Alternativa a la clave FIRMS_MAP_KEY para cargar la serie histórica:

1. Entra a https://firms.modaps.eosdis.nasa.gov/download/ → **Create New Request**.
2. Área: **Country → Peru**. Fuente: **VIIRS S-NPP** (repite luego con **VIIRS NOAA-20**). Formato: **CSV**.
   Fechas: un año por pedido (2020, 2021, …) para que cada zip pese menos de 25 MB.
3. FIRMS te envía por correo un enlace a un zip `DL_FIRE_…zip`. Descárgalo y súbelo sin descomprimir a esta carpeta
   (Add file → Upload files → Commit changes).
4. El flujo "Focos 2020–hoy – carga histórica" lo procesa solo, lo guarda en `data/archivo/focos_historico/`,
   borra el zip y vuelve a publicar la plataforma.
