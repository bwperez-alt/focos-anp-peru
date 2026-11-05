"""Clima y pronóstico a 3 días por ANP – Open-Meteo (modelos meteorológicos globales y regionales, sin token).

Fuente: https://open-meteo.com/en/docs (licencia CC BY 4.0)
Se consulta el punto central de cada ANP de administración nacional y zona reservada.
Umbrales de aviso (orientativos, documentados en UMBRALES):
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from .aire_modelo import puntos_anp

URL = "https://api.open-meteo.com/v1/forecast"
FUENTE_WEB = "https://open-meteo.com/en/docs"
H = {"User-Agent": "observatorio-ambiental-anp-peru (investigacion academica; github.com/bwperez-alt/focos-anp-peru)"}
DIARIAS = ["weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_sum", "precipitation_probability_max",
           "wind_gusts_10m_max", "uv_index_max"]
UMBRALES = {
    "lluvia_fuerte_mm": 30,   # precipitación diaria
    "lluvia_moderada_mm": 15,
    "helada_c": 0,            # temperatura mínima
    "calor_c": 33,            # temperatura máxima
    "viento_kmh": 60,         # ráfagas máximas
    "uv_extremo": 11,         # índice UV máximo
    "uv_muy_alto": 8,
}
LOTE = 40
# Código WMO del estado del tiempo -> texto breve
WMO = {0: "Despejado", 1: "Mayormente despejado", 2: "Parcialmente nublado", 3: "Nublado", 45: "Niebla", 48: "Niebla con escarcha",
       51: "Llovizna ligera", 53: "Llovizna", 55: "Llovizna intensa", 61: "Lluvia ligera", 63: "Lluvia", 65: "Lluvia intensa",
       66: "Lluvia helada", 67: "Lluvia helada intensa", 71: "Nevada ligera", 73: "Nevada", 75: "Nevada intensa", 77: "Granizo fino",
       80: "Chubascos ligeros", 81: "Chubascos", 82: "Chubascos fuertes", 85: "Chubascos de nieve", 86: "Chubascos de nieve fuertes",
       95: "Tormenta", 96: "Tormenta con granizo", 99: "Tormenta con granizo fuerte"}


def avisos_dia(d: dict) -> list[str]:
    a = []
    if (d.get("lluvia_mm") or 0) >= UMBRALES["lluvia_fuerte_mm"]:
        a.append("lluvia_fuerte")
    elif (d.get("lluvia_mm") or 0) >= UMBRALES["lluvia_moderada_mm"]:
        a.append("lluvia_moderada")
    if d.get("tmin") is not None and d["tmin"] <= UMBRALES["helada_c"]:
        a.append("helada")
    if d.get("tmax") is not None and d["tmax"] >= UMBRALES["calor_c"]:
        a.append("calor")
    if (d.get("rafaga_kmh") or 0) >= UMBRALES["viento_kmh"]:
        a.append("viento")
    if (d.get("uv") or 0) >= UMBRALES["uv_extremo"]:
        a.append("uv_extremo")
    elif (d.get("uv") or 0) >= UMBRALES["uv_muy_alto"]:
        a.append("uv_muy_alto")
    if d.get("codigo") in (95, 96, 99):
        a.append("tormenta")
    return a


def ejecutar(salida: Path, capas_anp) -> dict:
    puntos = puntos_anp(capas_anp)
    areas = []
    for i in range(0, len(puntos), LOTE):
        lote = puntos[i:i + LOTE]
        r = requests.get(URL, headers=H, timeout=90, params={
            "latitude": ",".join(str(p["lat"]) for p in lote), "longitude": ",".join(str(p["lon"]) for p in lote),
            "daily": ",".join(DIARIAS), "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
            "forecast_days": 3, "timezone": "America/Lima"})
        r.raise_for_status()
        resp = r.json()
        for p, d in zip(lote, resp if isinstance(resp, list) else [resp]):
            dd = d.get("daily", {})
            dias = []
            for k, fecha in enumerate(dd.get("time", [])):
                v = lambda c: (dd.get(c) or [None] * 3)[k]
                dia = {"fecha": fecha, "codigo": v("weather_code"), "estado": WMO.get(v("weather_code"), ""),
                       "tmax": v("temperature_2m_max"), "tmin": v("temperature_2m_min"), "lluvia_mm": v("precipitation_sum"),
                       "prob_lluvia": v("precipitation_probability_max"), "rafaga_kmh": v("wind_gusts_10m_max"), "uv": v("uv_index_max")}
                dia["avisos"] = avisos_dia(dia)
                dias.append(dia)
            cur = d.get("current", {})
            areas.append({**p, "elevacion": d.get("elevation"),
                          "ahora": {"temp": cur.get("temperature_2m"), "humedad": cur.get("relative_humidity_2m"),
                                    "lluvia_mm": cur.get("precipitation"), "estado": WMO.get(cur.get("weather_code"), ""),
                                    "viento_kmh": cur.get("wind_speed_10m"), "hora": (cur.get("time") or "").replace("T", " ")},
                          "dias": dias})
    if not areas:
        raise RuntimeError("Open-Meteo no devolvió pronósticos")
    conteo = {}
    for a in areas:
        for av in {x for d in a["dias"][:2] for x in d["avisos"]}:
            conteo[av] = conteo.get(av, 0) + 1
    res = {"fuente": "Open-Meteo (modelos meteorológicos de servicios nacionales, incl. NOAA GFS, DWD ICON, ECMWF)", "url": FUENTE_WEB,
           "licencia": "CC BY 4.0", "generado": datetime.now(timezone.utc).isoformat(timespec="minutes"), "umbrales": UMBRALES,
           "nota": "Pronóstico en el punto central de cada ANP; en áreas grandes o de relieve abrupto las condiciones varían localmente.",
           "avisos_48h": conteo, "areas": areas}
    (salida / "clima.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    return {"ultimo_dato": areas[0]["ahora"]["hora"] or res["generado"][:16], "registros": len(areas)}
