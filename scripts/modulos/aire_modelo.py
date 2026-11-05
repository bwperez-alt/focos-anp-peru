"""Calidad del aire estimada por modelo en cada ANP – Copernicus CAMS vía Open-Meteo (sin token).

Fuente: https://open-meteo.com/en/docs/air-quality-api  (datos CAMS, licencia CC BY 4.0)
Modelo: CAMS global (~40 km) y, donde existe, el dominio regional de mayor resolución.
Son valores MODELADOS (no mediciones de estación): útiles para ver tendencias regionales,
humo de incendios y polvo, pero pueden subestimar picos urbanos locales.

Indicadores por ANP (punto central del área):
  PM2,5 y PM10: promedio de las últimas 24 h, valor de la última hora y máximo previsto en las próximas 24 h,
  comparados con el ECA (D.S. 003-2017-MINAM) y la guía OMS 2021.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
FUENTE_WEB = "https://open-meteo.com/en/docs/air-quality-api"
H = {"User-Agent": "observatorio-ambiental-anp-peru (investigacion academica; github.com/bwperez-alt/focos-anp-peru)"}
VARIABLES = ["pm2_5", "pm10", "ozone", "nitrogen_dioxide", "carbon_monoxide", "dust"]
ECA = {"pm2_5": 50, "pm10": 100}   # 24 h, D.S. 003-2017-MINAM
OMS = {"pm2_5": 15, "pm10": 45}    # 24 h, guías OMS 2021
LOTE = 40


def puntos_anp(capas_anp) -> list[dict]:
    """Punto representativo (centro del rectángulo envolvente promedio) de cada ANP nacional y zona reservada."""
    out = []
    for _, capa in capas_anp[:2]:
        for it in capa.items:
            lo = float(np.mean([(p[2][0] + p[3][0]) / 2 for p in it["partes"]]))
            la = float(np.mean([(p[2][1] + p[3][1]) / 2 for p in it["partes"]]))
            out.append({"area": it["nombre"], "categoria": it["extra"].get("cat", ""), "lon": round(lo, 3), "lat": round(la, 3)})
    return out


def consultar(puntos: list[dict]) -> list[dict]:
    respuestas = []
    for i in range(0, len(puntos), LOTE):
        lote = puntos[i:i + LOTE]
        params = {
            "latitude": ",".join(str(p["lat"]) for p in lote),
            "longitude": ",".join(str(p["lon"]) for p in lote),
            "hourly": ",".join(VARIABLES),
            "past_days": 1, "forecast_days": 2, "timezone": "America/Lima",
        }
        r = requests.get(URL, params=params, headers=H, timeout=90)
        r.raise_for_status()
        d = r.json()
        respuestas.extend(d if isinstance(d, list) else [d])
    return respuestas


def resumir(puntos: list[dict], respuestas: list[dict], ahora: pd.Timestamp) -> tuple[list[dict], pd.DataFrame]:
    filas, horario = [], []
    for p, resp in zip(puntos, respuestas):
        h = resp.get("hourly") or {}
        if not h.get("time"):
            continue
        df = pd.DataFrame(h)
        df["time"] = pd.to_datetime(df["time"])
        pasado = df[(df.time <= ahora) & (df.time > ahora - pd.Timedelta(hours=24))]
        futuro = df[(df.time > ahora) & (df.time <= ahora + pd.Timedelta(hours=24))]
        ult = df[df.time <= ahora].tail(1)
        r = {**p}
        for v in ["pm2_5", "pm10"]:
            prom = pasado[v].dropna()
            r[f"{v}_24h"] = round(float(prom.mean()), 1) if len(prom) >= 18 else None
            r[f"{v}_ahora"] = None if ult.empty or pd.isna(ult[v].iat[0]) else round(float(ult[v].iat[0]), 1)
            r[f"{v}_max_prox24h"] = None if futuro[v].dropna().empty else round(float(futuro[v].max()), 1)
            if r[f"{v}_24h"] is not None:
                r[f"{v}_pct_eca"] = round(100 * r[f"{v}_24h"] / ECA[v], 1)
                r[f"{v}_pct_oms"] = round(100 * r[f"{v}_24h"] / OMS[v], 1)
        for v in ["ozone", "nitrogen_dioxide", "carbon_monoxide", "dust"]:
            r[f"{v}_ahora"] = None if ult.empty or pd.isna(ult[v].iat[0]) else round(float(ult[v].iat[0]), 1)
        r["serie"] = {"t": [t.strftime("%m-%d %H") for t in df.time],
                      "pm2_5": [None if pd.isna(x) else round(float(x), 1) for x in df.pm2_5]}
        filas.append(r)
        horario.append(df[df.time <= ahora].assign(area=p["area"], lon=p["lon"], lat=p["lat"]))
    hist = pd.concat(horario, ignore_index=True) if horario else pd.DataFrame()
    return filas, hist


def ejecutar(salida: Path, archivo: Path, capas_anp) -> dict:
    ahora = pd.Timestamp.now(tz="America/Lima").tz_localize(None).floor("h")
    puntos = puntos_anp(capas_anp)
    filas, hist = resumir(puntos, consultar(puntos), ahora)
    if not filas:
        raise RuntimeError("Open-Meteo no devolvió datos")
    filas.sort(key=lambda r: -(r.get("pm2_5_24h") or 0))
    validos = [r for r in filas if r.get("pm2_5_24h") is not None]
    res = {
        "fuente": "Copernicus Atmosphere Monitoring Service (CAMS) vía Open-Meteo",
        "url": FUENTE_WEB,
        "licencia": "CC BY 4.0 – contiene datos modificados del Copernicus Atmosphere Monitoring Service",
        "nota": "Valores estimados por modelo en el punto central de cada ANP (resolución ~10–40 km); no son mediciones de estación.",
        "generado": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "hora_referencia": ahora.strftime("%Y-%m-%d %H:%M"),
        "eca": ECA, "oms": OMS,
        "resumen": {
            "n_areas": len(filas),
            "sobre_eca_pm25": sum(1 for r in validos if r["pm2_5_24h"] > ECA["pm2_5"]),
            "sobre_oms_pm25": sum(1 for r in validos if r["pm2_5_24h"] > OMS["pm2_5"]),
            "max_pm25_24h": validos[0]["pm2_5_24h"] if validos else None,
            "area_max": validos[0]["area"] if validos else None,
            "mediana_pm25_24h": round(float(np.median([r["pm2_5_24h"] for r in validos])), 1) if validos else None,
        },
        "areas": filas,
    }
    (salida / "aire_modelo.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    if not hist.empty:
        hist = hist.assign(time=hist.time.dt.strftime("%Y-%m-%d %H:%M")).rename(columns={"time": "fecha_hora"})
        cols = ["fecha_hora", "area", "lon", "lat"] + VARIABLES
        for dia, parte in hist[cols].groupby(hist.fecha_hora.str[:10]):
            f = archivo / "aire_modelo" / dia[:7] / f"aire_modelo_{dia}.csv"
            f.parent.mkdir(parents=True, exist_ok=True)
            if f.exists():
                parte = pd.concat([pd.read_csv(f), parte], ignore_index=True)
            parte.drop_duplicates(subset=["fecha_hora", "area"], keep="last").sort_values(["fecha_hora", "area"]).to_csv(f, index=False)
    return {"ultimo_dato": res["hora_referencia"], "registros": len(filas), "via": "Open-Meteo / CAMS"}
