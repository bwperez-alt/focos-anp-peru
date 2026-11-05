# Fuego en las Áreas Naturales Protegidas del Perú

Observatorio automático de **focos de calor satelitales** (NASA FIRMS) cruzados con las **Áreas Naturales Protegidas** y sus **zonas de amortiguamiento** (SERNANP). Se actualiza solo cada 6 horas con GitHub Actions y se publica gratis en GitHub Pages.

**Dashboard:** https://bwperez-alt.github.io/focos-anp-peru/

> Un foco de calor no equivale a un incendio confirmado. Las cifras muestran el método y sirven para priorizar verificación en campo, no para diagnosticar.

## Método

| Paso | Qué se hace |
|---|---|
| 1. Fuente | Archivos públicos de NASA FIRMS (VIIRS 375 m: S-NPP, NOAA-20, NOAA-21), últimos 7 días. No requiere clave. |
| 2. Limpieza | Recorte al contorno del Perú; descarte de confianza baja; duplicados exactos; **fuentes persistentes** (celdas de ~400 m con focos en ≥ 4 días distintos: antorchas de gas, industrias). |
| 3. Eventos | Agrupación espacio-temporal con DBSCAN (1 km; 1 día ≈ 1 km) para no contar dos veces un mismo fuego. |
| 4. Territorio | Cada foco se clasifica como *Dentro de ANP* (nacional, zona reservada, ACR, ACP), *Zona de amortiguamiento* o *Fuera de ANP*, y se asigna a su departamento. |
| 5. Indicadores | Focos y eventos por zona, ranking de áreas, serie diaria y departamentos → `docs/data/resumen.json`. |

Los parámetros están al inicio de `scripts/pipeline.py`.

## Estructura

```
.github/workflows/actualizar.yml  tarea programada (cada 6 h) + publicación en Pages
scripts/pipeline.py               captura → limpieza → eventos → cruce → indicadores
scripts/actualizar_capas_base.py  vuelve a descargar las capas del SERNANP (manual)
scripts/vista_previa.py           genera un HTML autocontenido para compartir sin servidor
data/base/                        capas oficiales (ANP, ZR, ACR, ACP, ZA, departamentos)
data/archivo/                     histórico mensual de focos (CSV) para investigación
docs/                             sitio web (index.html + data/)
```

## Ejecutar en tu computadora

```bash
pip install -r requirements.txt
python scripts/pipeline.py            # descarga y procesa los últimos 7 días
python -m http.server -d docs 8000    # abre http://localhost:8000
```

## Fuentes y licencias

- NASA FIRMS – VIIRS 375 m Active Fire NRT. NASA solicita citar: *"We acknowledge the use of data and/or imagery from NASA's FIRMS (https://earthdata.nasa.gov/firms), part of NASA's Earth Science Data and Information System (ESDIS)."*
- SERNANP – GeoServicios (`servicios_ogc/peru_sernanp_0102` y `peru_sernanp_0214`). Geometrías simplificadas (~300 m) para la web.
- Límites departamentales: INEI, vía [juaneladio/peru-geojson](https://github.com/juaneladio/peru-geojson).
- Mapa base © CARTO © OpenStreetMap.

**Autor:** Mg. Pérez Flores, Brandon W. · GreenPulse SAC
