"""Clima y pronóstico por ANP – Open-Meteo (modelos meteorológicos globales y regionales, sin token).

Fuente: https://open-meteo.com/en/docs  (licencia CC BY 4.0)
Para cada ANP (punto central): pronóstico diario de 3 días y condiciones de las últimas 24 h.
Señales para el ecoturismo (umbrales explícitos en UMBRALES):
  lluvia intensa, helada, viento fuerte, calor extremo y radiación UV extrema;
  además, un índice simple de "condiciones secas" (días sin lluvia) útil para el riesgo de incendio.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .aire_modelo import puntos_anp

URL = "https://api.open-meteo.com/v1/forecast"
FUENTE_WEB = "https://open-meteo.com/en/docs"
H = {"User-Agent": "observatorio-ambiental-anp-peru (investigacion academica; github.com/bwperez-alt/focos-anp-peru)"}
DIARIO = ["weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_sum", "precipitation_probability_max",
          "wind_gusts_10m_max", "uv_index_max", "et0_fao_evapotranspiration"]
UMBRALES = {
    "lluvia_intensa_mm": 40,    # precipitación diaria prevista
    "helada_c": -3,             # temperatura mínima prevista
    "viento_fuerte_kmh": 60,    # ráfagas máximas previstas
    "calor_c": 35,              # temperatura máxima prevista
    "uv_extremo": 11,           # índice UV máximo previsto (escala OMS)
    "dias_secos": 10,           # días consecutivos con < 1 mm (condición favorable al fuego)
}
LOTE = 40

CODIGOS = {0: "Despejado", 1: "Mayormente despejado", 2: "Parcialmente nublado", 3: "Nublado", 45: "Niebla", 48: "Niebla con escarcha",
           51: "Llovizna ligera", 53: "Llovizna", 55: "Llovizna intensa", 61: "Lluvia ligera", 63: "Lluvia", 65: "Lluvia intensa",
           71: "Nevada ligera", 73: "Nevada", 75: "Nevada intensa", 77: "Granizo fino", 80: "Chubascos ligeros", 81: "Chubascos",
           82: "Chubascos fuertes", 85: "Chubascos de nieve", 86: "Chubascos de nieve fuertes", 95: "Tormenta", 96: "Tormenta con granizo",
           99: "Tormenta fuerte con granizo"}


def consultar(puntos: list[dict]) -> list[dict]:
    out = []
    for i in range(0, len(puntos), LOTE):
        lote = puntos[i:i + LOTE]
        params = {"latitude": ",".join(str(p["lat"]) for p in lote), "longitude": ",".join(str(p["lon"]) for p in lote),
                  "daily": ",".join(DIARIO), "past_days": 14, "forecast_days": 3, "timezone": "America/Lima"}
        r = requests.get(URL, params=params, headers=H, timeout=90)
        r.raise_for_status()
        d = r.json()
        out.extend(d if isinstance(d, list) else [d])
    return out


def evaluar(p: dict, resp: dict, hoy: pd.Timestamp) -> dict | None:
    d = resp.get("daily") or {}
    if not d.get("time"):
        return None
    df = pd.DataFrame(d)
    df["time"] = pd.to_datetime(df["time"])
    pron = df[df.time >= hoy].head(3)
    pasado = df[df.time < hoy]
    secos = 0
    for v in pasado.precipitation_sum.fillna(0)[::-1]:
        if v < 1:
            secos += 1
        else:
            break
    dias = [{
        "fecha": r.time.strftime("%Y-%m-%d"), "estado": CODIGOS.get(int(r.weather_code), "—") if pd.notna(r.weather_code) else "—",
        "tmax": None if pd.isna(r.temperature_2m_max) else round(float(r.temperature_2m_max)),
        "tmin": None if pd.isna(r.temperature_2m_min) else round(float(r.temperature_2m_min)),
        "lluvia_mm": None if pd.isna(r.precipitation_sum) else round(float(r.precipitation_sum), 1),
        "prob_lluvia": None if pd.isna(r.precipitation_probability_max) else int(r.precipitation_probability_max),
        "rafagas_kmh": None if pd.isna(r.wind_gusts_10m_max) else round(float(r.wind_gusts_10m_max)),
        "uv": None if pd.isna(r.uv_index_max) else round(float(r.uv_index_max), 1),
    } for r in pron.itertuples()]
    alertas = []
    U = UMBRALES
    for dd in dias:
        f = pd.Timestamp(dd["fecha"]).strftime("%d/%m")
        if (dd["lluvia_mm"] or 0) >= U["lluvia_intensa_mm"]:
            alertas.append(f"Lluvia intensa prevista ({dd['lluvia_mm']} mm el {f})")
        if dd["tmin"] is not None and dd["tmin"] <= U["helada_c"]:
            alertas.append(f"Helada prevista ({dd['tmin']} °C el {f})")
        if (dd["rafagas_kmh"] or 0) >= U["viento_fuerte_kmh"]:
            alertas.append(f"Ráfagas de {dd['rafagas_kmh']} km/h el {f}")
        if dd["tmax"] is not None and dd["tmax"] >= U["calor_c"]:
            alertas.append(f"Calor extremo ({dd['tmax']} °C el {f})")
    avisos = []
    if any((dd["uv"] or 0) >= U["uv_extremo"] for dd in dias):
        avisos.append(f"Radiación UV extrema (índice {max(dd['uv'] or 0 for dd in dias)})")
    if secos >= U["dias_secos"]:
        avisos.append(f"{secos} días sin lluvia: vegetación seca, mayor riesgo de incendio")
    return {**p, "dias": dias, "dias_secos": secos, "lluvia_14d_mm": round(float(pasado.precipitation_sum.fillna(0).sum()), 1),
            "alertas": list(dict.fromkeys(alertas)), "avisos": avisos}


def ejecutar(salida: Path, archivo: Path, capas_anp) -> dict:
    hoy = pd.Timestamp.now(tz="America/Lima").tz_localize(None).normalize()
    puntos = puntos_anp(capas_anp)
    filas = [x for x in (evaluar(p, r, hoy) for p, r in zip(puntos, consultar(puntos))) if x]
    if not filas:
        raise RuntimeError("Open-Meteo no devolvió pronósticos")
    filas.sort(key=lambda r: (-len(r["alertas"]), -len(r["avisos"]), r["area"]))
    res = {"fuente": "Open-Meteo (modelos meteorológicos de servicios nacionales: ECMWF, NOAA GFS, DWD ICON, entre otros)",
           "url": FUENTE_WEB, "licencia": "CC BY 4.0", "umbrales": UMBRALES,
           "generado": datetime.now(timezone.utc).isoformat(timespec="minutes"), "fecha": hoy.strftime("%Y-%m-%d"),
           "resumen": {"n_areas": len(filas), "con_alertas": sum(1 for r in filas if r["alertas"]),
                       "lluvia_intensa": sum(1 for r in filas if any("Lluvia" in a for a in r["alertas"])),
                       "heladas": sum(1 for r in filas if any("Helada" in a for a in r["alertas"])),
                       "secas": sum(1 for r in filas if r["dias_secos"] >= UMBRALES["dias_secos"])},
           "areas": filas}
    (salida / "clima.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    # serie histórica: pronóstico del día emitido hoy (una fila por ANP y día de emisión)
    filas_csv = [{"emitido": res["fecha"], "area": r["area"], "lon": r["lon"], "lat": r["lat"], "dias_secos": r["dias_secos"],
                  "lluvia_14d_mm": r["lluvia_14d_mm"], **{f"{k}_d0": r["dias"][0][k] for k in ["tmax", "tmin", "lluvia_mm", "rafagas_kmh", "uv"]}}
                 for r in filas if r["dias"]]
    f = archivo / "clima" / f"clima_{res['fecha'][:7]}.csv"
    f.parent.mkdir(parents=True, exist_ok=True)
    nuevo = pd.DataFrame(filas_csv)
    if f.exists():
        nuevo = pd.concat([pd.read_csv(f), nuevo], ignore_index=True)
    nuevo.drop_duplicates(subset=["emitido", "area"], keep="last").to_csv(f, index=False)
    return {"ultimo_dato": res["generado"][:16].replace("T", " "), "registros": len(filas), "via": "Open-Meteo"}
