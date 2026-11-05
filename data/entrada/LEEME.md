# Carga manual de alertas de deforestación (Geobosques)

Geobosques (PNCB – MINAM) bloquea las descargas automáticas desde fuera del Perú.
Para actualizar el módulo de deforestación (recomendado: una vez al mes):

1. Entra a https://geobosques.minam.gob.pe/geobosque/view/descargas.php
2. Categoría **ALERTA TEMPRANA DE DEFORESTACIÓN (ATD)** → descarga **"Alertas Tempranas 2026 – PNCB (Puntos)"**.
   El archivo se llama `Alertas_PNCB_shape_2026.zip` (unos 13 MB). No lo descomprimas.
3. En GitHub, abre esta carpeta (`data/entrada`) → **Add file → Upload files** → arrastra el zip → **Commit changes**.
   Si ya existe un zip del mismo año, súbelo igual: GitHub lo reemplaza.

La plataforma lo procesa sola en unos minutos (cruce con ANP y zonas de amortiguamiento) y publica los resultados.
