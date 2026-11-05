# Observatorio Ambiental de las Áreas Naturales Protegidas del Perú

Plataforma abierta que integra **fuego, deforestación, calidad del aire, emergencias y sismos** con los límites oficiales de las **Áreas Naturales Protegidas (ANP)** y sus **zonas de amortiguamiento** del SERNANP. Con esa información genera un **semáforo para el ecoturismo** por ANP. Se actualiza **cada hora** con GitHub Actions y se publica gratis en GitHub Pages. Además, guarda una **serie histórica descargable** para investigación y docencia.

**Plataforma:** https://bwperez-alt.github.io/focos-anp-peru/

## Módulos y fuentes

| Módulo | Fuente oficial | Frecuencia de la fuente | Acceso desde la nube |
|---|---|---|---|
| Focos de calor | NASA FIRMS – VIIRS 375 m (S-NPP, NOAA-20, NOAA-21) | ~3 h | Directo |
| Límites de ANP y ZA | SERNANP – GeoServicios | Estable | Copia en `data/base` |
| Calidad del aire estimada (todas las ANP) | Copernicus CAMS vía Open-Meteo (modelo, CC BY 4.0) | Horaria | Directo, sin token |
| Calidad del aire medida (Lima) | SENAMHI – red de Lima Metropolitana | Horaria | Opcional, vía WAQI (aqicn.org), que retransmite las estaciones del SENAMHI. El SENAMHI no acepta conexiones desde fuera del Perú. |
| Deforestación | PNCB – MINAM, Geobosques (alertas tempranas, puntos) | Semanas | Carga manual (ver abajo). Geobosques bloquea descargas automáticas desde fuera del Perú. |
| Emergencias | INDECI – COEN (RSS oficial de reportes) | Minutos | Directo |
| Clima y pronóstico (3 días) por ANP | Open-Meteo (CC BY 4.0) | Horaria | Directo, sin token |
| Visitas mensuales a ANP (2019 → último mes publicado) | MINCETUR – Datos Turismo, con datos del SERNANP (9 ANP con registro propio) | Mensual (1–2 meses de desfase) | Directo (exportación oficial) |
| Flujo turístico por región | MINCETUR – arribos a establecimientos de hospedaje | Mensual (acumulado del año) | Directo |
| Visitas detalladas por ANP (sector, procedencia, edad) | SERNANP – Plataforma Nacional de Datos Abiertos | Último corte publicado (2022–2023) | Directo |
| Registro de deforestación en ANP (con causas) | SERNANP – Plataforma Nacional de Datos Abiertos | Anual | Directo |
| Pérdida de bosque 2001–2025 por ANP y ZA | Hansen et al., Global Forest Change v1.13 (UMD, CC BY 4.0) | Anual | Workflow `bosques-anual` |
| Sismos | USGS FDSN Event Service. El servicio de datos del IGP no está disponible públicamente. | Minutos | Directo |
| Ecoturismo | Semáforo integrado (reglas en `scripts/modulos/ecoturismo.py`) | Horaria | — |

Si una fuente falla, la plataforma conserva el último dato publicado y lo indica en la franja **"estado de las fuentes"**.

## Configuración (una sola vez)

1. **Pages:** Settings → Pages → Source: **GitHub Actions**.
2. **Opcional, mediciones de estación del SENAMHI:** pide un token gratuito en https://aqicn.org/data-platform/token/ y guárdalo en Settings → Secrets and variables → Actions → **New repository secret** con el nombre `WAQI_TOKEN`.

### Deforestación

Una vez al mes, descarga de Geobosques **"Alertas Tempranas 2026 – PNCB (Puntos)"** (`Alertas_PNCB_shape_2026.zip`) y súbelo sin descomprimir a la carpeta `data/entrada/` (Add file → Upload files). Las instrucciones detalladas están en [`data/entrada/LEEME.md`](data/entrada/LEEME.md).

## Método (resumen)

- **Fuego:** recorte al Perú → descarte de confianza baja, duplicados y fuentes persistentes (celdas de ~400 m con focos en ≥ 4 días distintos) → eventos con DBSCAN espacio-temporal (1 km; 1 día ≈ 1 km) → cruce con ANP/ZA y departamentos.
- **Deforestación:** lectura del shapefile oficial (UTM 18S → WGS84) → cruce con ANP/ZA → serie mensual, ranking por área y rejilla de 0,05° de los últimos 90 días.
- **Aire estimado:** PM2,5, PM10, O₃, NO₂, CO y polvo horarios del modelo CAMS en el punto central de cada ANP; promedio de 24 h, valor actual y máximo previsto para las próximas 24 h. Son valores modelados (~10–40 km), no mediciones.
- **Aire medido:** promedios móviles de 24 h de PM2,5 y PM10 frente al ECA (D.S. 003-2017-MINAM: 50 y 100 µg/m³) y a la guía de la OMS 2021 (15 y 45 µg/m³). Por la vía WAQI, el índice AQI se convierte a µg/m³ con los puntos de corte de la US EPA y el promedio de 24 h se calcula con el historial horario propio.
- **Emergencias:** del título de cada reporte del COEN se extraen tipo, distrito y departamento. Cada emergencia se ubica en el centroide del distrito (INEI) y se cruza con ANP/ZA.
- **Fichas de visita:** infografía por ANP con semáforo, condiciones actuales, pronóstico a 3 días, perfil de visitantes y bosque. Las recomendaciones se generan cada hora: unas dependen de las condiciones (fuego, aire, lluvia, helada, calor, viento, UV, sismos, emergencias, temporada alta) y otras son de base según el ecosistema (marino-costero, costa, altoandino, montaña, amazonía).
- **Bosques:** suma por polígono del área de los píxeles de 30 m con pérdida en cada año (Hansen); las zonas de amortiguamiento excluyen la superficie del ANP.
- **Semáforo:** reglas explícitas por ANP (fuego, emergencias INDECI, sismos y calidad del aire). Ver `REGLAS` en `scripts/modulos/ecoturismo.py`.

## Datos para investigación (`data/archivo/`)

- `focos/AAAA-MM/focos_AAAA-MM-DD.csv`: focos clasificados por zona, área y departamento.
- `aire_modelo/AAAA-MM/aire_modelo_AAAA-MM-DD.csv`: calidad del aire horaria estimada por ANP (CAMS).
- `aire/AAAA-MM/aire_AAAA-MM-DD.csv`: mediciones horarias por estación (si hay acceso al SENAMHI).
- `visitas_anp_mincetur.csv`: visitas mensuales oficiales por ANP (nacionales, extranjeros, total) desde 2019.
- `arribos_hospedaje_region.csv`: arribos a hospedajes por región (acumulado del año y variación).
- `hansen_perdida_anp_ha.csv`: pérdida de bosque anual por ANP y zona de amortiguamiento (ha).
- `sernanp/`: copias de los conjuntos del SERNANP (visitas y registro de deforestación).
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
