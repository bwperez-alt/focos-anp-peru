# Observatorio Ambiental de las Áreas Naturales Protegidas del Perú

Plataforma abierta que integra **fuego, deforestación, calidad del aire, emergencias y sismos** con los límites oficiales de las **Áreas Naturales Protegidas (ANP)** y sus **zonas de amortiguamiento** del SERNANP. Con esa información genera un **semáforo para el ecoturismo** por ANP. Se actualiza **cada hora** con GitHub Actions y se publica gratis en GitHub Pages. Además, guarda una **serie histórica descargable** para investigación y docencia.

**Plataforma:** https://bwperez-alt.github.io/focos-anp-peru/

## Módulos y fuentes

| Módulo | Fuente oficial | Frecuencia de la fuente | Acceso desde la nube |
|---|---|---|---|
| Focos de calor | NASA FIRMS – VIIRS 375 m (S-NPP, NOAA-20, NOAA-21) | ~3 h | Directo |
| Límites de ANP y ZA | SERNANP – GeoServicios | Estable | Copia en `data/base` |
| Calidad del aire | SENAMHI – red de Lima Metropolitana | Horaria | Vía WAQI (aqicn.org), que retransmite las estaciones del SENAMHI. El SENAMHI no acepta conexiones desde fuera del Perú. |
| Deforestación | PNCB – MINAM, Geobosques (alertas tempranas, puntos) | Semanas | Carga manual (ver abajo). Geobosques bloquea descargas automáticas desde fuera del Perú. |
| Emergencias | INDECI – COEN (RSS oficial de reportes) | Minutos | Directo |
| Sismos | USGS FDSN Event Service. El servicio de datos del IGP no está disponible públicamente. | Minutos | Directo |
| Ecoturismo | Semáforo integrado (reglas en `scripts/modulos/ecoturismo.py`) | Horaria | — |

Si una fuente falla, la plataforma conserva el último dato publicado y lo indica en la franja **"estado de las fuentes"**.

## Configuración (una sola vez)

1. **Pages:** Settings → Pages → Source: **GitHub Actions**.
2. **Calidad del aire:** pide un token gratuito en https://aqicn.org/data-platform/token/ y guárdalo en Settings → Secrets and variables → Actions → **New repository secret** con el nombre `WAQI_TOKEN`.

### Deforestación

Una vez al mes, descarga de Geobosques **"Alertas Tempranas 2026 – PNCB (Puntos)"** (`Alertas_PNCB_shape_2026.zip`) y súbelo sin descomprimir a la carpeta `data/entrada/` (Add file → Upload files). Las instrucciones detalladas están en [`data/entrada/LEEME.md`](data/entrada/LEEME.md).

## Método (resumen)

- **Fuego:** recorte al Perú → descarte de confianza baja, duplicados y fuentes persistentes (celdas de ~400 m con focos en ≥ 4 días distintos) → eventos con DBSCAN espacio-temporal (1 km; 1 día ≈ 1 km) → cruce con ANP/ZA y departamentos.
- **Deforestación:** lectura del shapefile oficial (UTM 18S → WGS84) → cruce con ANP/ZA → serie mensual, ranking por área y rejilla de 0,05° de los últimos 90 días.
- **Aire:** promedios móviles de 24 h de PM2,5 y PM10 frente al ECA (D.S. 003-2017-MINAM: 50 y 100 µg/m³) y a la guía de la OMS 2021 (15 y 45 µg/m³). Por la vía WAQI, el índice AQI se convierte a µg/m³ con los puntos de corte de la US EPA y el promedio de 24 h se calcula con el historial horario propio.
- **Emergencias:** del título de cada reporte del COEN se extraen tipo, distrito y departamento. Cada emergencia se ubica en el centroide del distrito (INEI) y se cruza con ANP/ZA.
- **Semáforo:** reglas explícitas por ANP (fuego, emergencias INDECI, sismos y calidad del aire). Ver `REGLAS` en `scripts/modulos/ecoturismo.py`.

## Datos para investigación (`data/archivo/`)

- `focos/AAAA-MM/focos_AAAA-MM-DD.csv`: focos clasificados por zona, área y departamento.
- `aire/AAAA-MM/aire_AAAA-MM-DD.csv`: mediciones horarias por estación.
- `emergencias_indeci.csv`, `sismos.csv`, `deforestacion_resumen_AAAA.csv`, `historial_indicadores.csv`.

## Estructura

```
.github/workflows/actualizar.yml   corrida horaria + publicación en Pages
scripts/actualizar.py              orquestador (cada módulo falla de forma aislada)
scripts/pipeline.py                módulo de fuego (NASA FIRMS)
scripts/modulos/                   aire, deforestacion, riesgos, ecoturismo
data/base/                         capas oficiales (ANP, ZR, ACR, ACP, ZA, departamentos)
data/entrada/                      carga manual de Geobosques
data/archivo/                      serie histórica (CSV)
docs/                              sitio web
```

Para ejecutarlo localmente: `pip install -r requirements.txt && python scripts/actualizar.py && python -m http.server -d docs 8000`.

## Cómo citar

Pérez Flores, B. W. (2026). *Observatorio Ambiental de las Áreas Naturales Protegidas del Perú* [Plataforma web y conjunto de datos]. GreenPulse SAC. https://bwperez-alt.github.io/focos-anp-peru/

NASA solicita reconocer FIRMS: *"We acknowledge the use of data and/or imagery from NASA's FIRMS (https://earthdata.nasa.gov/firms), part of NASA's Earth Science Data and Information System (ESDIS)."*

## Limitaciones

Un foco de calor no equivale a un incendio confirmado, y las nubes ocultan fuegos. Las alertas de deforestación se publican con semanas de retraso. La ubicación de las emergencias es aproximada (centroide del distrito). El semáforo es una herramienta de priorización, no un cierre oficial.

**Autor:** Mg. Pérez Flores, Brandon W. · GreenPulse SAC · [LinkedIn](https://www.linkedin.com/in/brandon-perez-flores/)
