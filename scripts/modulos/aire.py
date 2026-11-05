"""Calidad del aire – SENAMHI (Red de monitoreo de Lima Metropolitana).

Fuente: https://www.senamhi.gob.pe/?p=calidad-del-aire  (datos horarios de las últimas ~48 h por estación)
Comparación normativa: ECA para Aire, D.S. N.° 003-2017-MINAM.
Referencia sanitaria: Guías de calidad del aire de la OMS (2021), PM2,5 y PM10 en 24 h.
"""
from __future__ import annotations

import html as htmlmod
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

URL = "https://www.senamhi.gob.pe/mapas/mapa-ca-monitoreo/map_data_ca.php"
FUENTE_WEB = "https://www.senamhi.gob.pe/?p=calidad-del-aire"
H = {"User-Agent": "Mozilla/5.0 (observatorio-ambiental-peru; investigacion academica)"}
CONTAMINANTES = ["PM2.5", "PM10", "SO2", "NO2", "O3", "CO"]

# ECA para aire (µg/m3) – D.S. 003-2017-MINAM
ECA = {
    "PM2.5": {"valor": 50, "periodo": "24 h"},
    "PM10": {"valor": 100, "periodo": "24 h"},
    "NO2": {"valor": 200, "periodo": "1 h"},
    "SO2": {"valor": 250, "periodo": "24 h"},
    "O3": {"valor": 100, "periodo": "8 h"},
    "CO": {"valor": 10000, "periodo": "8 h"},
}
HORAS = {"24 h": 24, "8 h": 8, "1 h": 1}
OMS = {"PM2.5": 15, "PM10": 45}  # Guías de calidad del aire OMS 2021, 24 h


def _limpio(s: str) -> str:
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def parsear(texto: str) -> tuple[pd.DataFrame, list[dict]]:
    i = texto.index("var locations = ")
    j = texto.index("];", i)
    bloque = texto[i + 16 : j + 1]
    # Cada estación: ['NOMBRE [..]', lat, lon, 'cod', '<html con tablas>']
    estaciones = []
    filas = []
    for m in re.finditer(r"\[\s*'((?:[^'\\]|\\.)*)'\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*'([^']*)'\s*,\s*'((?:[^'\\]|\\.)*)'(?:\s*,\s*'[^']*')*\s*\]", bloque, re.S):
        titulo, lat, lon, cod, cuerpo = m.groups()
        cuerpo = cuerpo.encode().decode("unicode_escape", errors="ignore") if "\\u" in cuerpo else cuerpo
        nombre = _limpio(titulo.split("[")[0])
        distrito = re.search(r"DISTRITO</td><td>([^<]*)", cuerpo)
        estaciones.append({"estacion": nombre.title(), "lat": float(lat), "lon": float(lon),
                           "distrito": (distrito.group(1).strip().title() if distrito else "")})
        tabla = cuerpo[cuerpo.find("<tbody>"): cuerpo.find("</tbody>")]
        for tr in re.findall(r"<tr>(.*?)</tr>", tabla, re.S):
            celdas = [_limpio(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if len(celdas) < 2 or not re.match(r"\d{2}/\d{2}/\d{4}", celdas[0]):
                continue
            fila = {"estacion": nombre.title(), "fecha_hora": f"{celdas[0]} {celdas[1]}"}
            for k, c in enumerate(CONTAMINANTES):
                v = celdas[2 + k] if 2 + k < len(celdas) else ""
                try:
                    fila[c] = float(v)
                except ValueError:
                    fila[c] = None
            filas.append(fila)
    df = pd.DataFrame(filas)
    if df.empty:
        return df, estaciones
    df["fecha_hora"] = pd.to_datetime(df.fecha_hora, format="%d/%m/%Y %H:%M")
    # CO en 0.00 suele indicar sensor sin dato
    df.loc[df.CO == 0, "CO"] = None
    return df.sort_values(["estacion", "fecha_hora"]), estaciones


def indicadores(df: pd.DataFrame, estaciones: list[dict]) -> dict:
    res = []
    for e in estaciones:
        d = df[df.estacion == e["estacion"]].set_index("fecha_hora").sort_index()
        if d.empty:
            continue
        ult = d.index.max()
        r = {**e, "ultimo": ult.strftime("%Y-%m-%d %H:%M"), "valores": {}, "eca": {}, "serie": {}}
        for c in CONTAMINANTES:
            s = d[c].dropna()
            if s.empty:
                continue
            h = HORAS[ECA[c]["periodo"]]
            ventana = s[s.index > ult - timedelta(hours=h)]
            prom = float(ventana.mean()) if len(ventana) >= max(1, int(h * 0.75)) else None
            r["valores"][c] = {"ultimo": round(float(s.iloc[-1]), 1), f"prom_{h}h": None if prom is None else round(prom, 1)}
            if prom is not None:
                r["eca"][c] = round(100 * prom / ECA[c]["valor"], 1)  # % del ECA
        # Referencia sanitaria internacional: guías OMS 2021 (24 h): PM2,5 = 15 µg/m3 ; PM10 = 45 µg/m3
        r["oms"] = {c: round(100 * r["valores"][c]["prom_24h"] / OMS[c], 1)
                    for c in OMS if r["valores"].get(c, {}).get("prom_24h") is not None}
        tail = d[d.index > ult - timedelta(hours=48)]
        r["serie"] = {"t": [x.strftime("%m-%d %H") for x in tail.index],
                      "PM2.5": [None if pd.isna(v) else round(v, 1) for v in tail["PM2.5"]],
                      "PM10": [None if pd.isna(v) else round(v, 1) for v in tail["PM10"]]}
        res.append(r)
    excede = [r["estacion"] for r in res if any(v > 100 for v in r["eca"].values())]
    return {
        "fuente": "SENAMHI – Red de Monitoreo Automático de la Calidad del Aire (Lima Metropolitana)",
        "url": FUENTE_WEB,
        "eca": ECA,
        "oms": OMS,
        "estaciones": res,
        "resumen": {
            "n_estaciones": len(res),
            "ultimo_dato": max((r["ultimo"] for r in res), default=None),
            "estaciones_sobre_eca": excede,
            "pm25_24h_max": max((r["valores"].get("PM2.5", {}).get("prom_24h") or 0 for r in res), default=None),
            "peor_estacion": max(res, key=lambda r: r["valores"].get("PM2.5", {}).get("prom_24h") or 0)["estacion"] if res else None,
        },
    }


# ------------------------------------------------------------------ respaldo en la nube: WAQI
# El SENAMHI no acepta conexiones desde fuera del Perú (los servidores de GitHub están en EE. UU.).
# World Air Quality Index (aqicn.org) retransmite en tiempo real las estaciones del SENAMHI, pero
# entrega índices AQI (escala US EPA); se convierten a concentración con los puntos de corte de la EPA.
WAQI = "https://api.waqi.info"
CORTES = {  # (C_baja, C_alta, I_baja, I_alta)
    "PM2.5": [(0, 12, 0, 50), (12.1, 35.4, 51, 100), (35.5, 55.4, 101, 150), (55.5, 150.4, 151, 200), (150.5, 250.4, 201, 300), (250.5, 500.4, 301, 500)],
    "PM10": [(0, 54, 0, 50), (55, 154, 51, 100), (155, 254, 101, 150), (255, 354, 151, 200), (355, 424, 201, 300), (425, 604, 301, 500)],
}


def aqi_a_conc(c: str, aqi: float | None) -> float | None:
    if aqi is None:
        return None
    for cl, ch, il, ih in CORTES[c]:
        if aqi <= ih:
            return round(cl + (aqi - il) * (ch - cl) / (ih - il), 1)
    return None


def leer_waqi(token: str) -> pd.DataFrame:
    b = requests.get(f"{WAQI}/map/bounds/?latlng=-18.6,-81.6,0.2,-68.5&token={token}", headers=H, timeout=60).json()
    if b.get("status") != "ok":
        raise RuntimeError(f"WAQI: {b.get('data')}")
    filas = []
    for st in b["data"]:
        f = requests.get(f"{WAQI}/feed/@{st['uid']}/?token={token}", headers=H, timeout=60).json()
        if f.get("status") != "ok":
            continue
        d = f["data"]
        atrib = " · ".join(a.get("name", "") for a in d.get("attributions", []))
        if "senamhi" not in atrib.lower():
            continue  # solo estaciones oficiales del SENAMHI
        iaqi = d.get("iaqi", {})
        v = lambda k: (iaqi.get(k) or {}).get("v")
        nombre = re.sub(r",\s*(Lima|Peru|Perú).*$", "", d["city"]["name"]).strip()
        filas.append({"estacion": nombre.title(), "lat": d["city"]["geo"][0], "lon": d["city"]["geo"][1],
                      "fecha_hora": d["time"]["s"][:16], "aqi_pm25": v("pm25"), "aqi_pm10": v("pm10"),
                      "PM2.5": aqi_a_conc("PM2.5", v("pm25")), "PM10": aqi_a_conc("PM10", v("pm10")),
                      "uid": st["uid"]})
    return pd.DataFrame(filas)


def ejecutar_waqi(salida: Path, archivo: Path, token: str) -> dict:
    nuevo = leer_waqi(token)
    if nuevo.empty:
        raise RuntimeError("WAQI no devolvió estaciones del SENAMHI")
    # Se acumula cada hora en el archivo diario; los promedios de 24 h salen de ese historial propio.
    archivo.mkdir(parents=True, exist_ok=True)
    for dia, parte in nuevo.groupby(nuevo.fecha_hora.str[:10]):
        f = archivo / "aire" / dia[:7] / f"aire_{dia}.csv"
        f.parent.mkdir(parents=True, exist_ok=True)
        if f.exists():
            parte = pd.concat([pd.read_csv(f), parte], ignore_index=True)
        parte.drop_duplicates(subset=["estacion", "fecha_hora"], keep="last").sort_values(["fecha_hora", "estacion"]).to_csv(f, index=False)
    hist = pd.concat([pd.read_csv(f) for f in sorted((archivo / "aire").glob("*/aire_*.csv"))[-3:]], ignore_index=True)
    hist["fecha_hora"] = pd.to_datetime(hist.fecha_hora)
    est = nuevo[["estacion", "lat", "lon"]].drop_duplicates("estacion").assign(distrito="").to_dict("records")
    res = indicadores(hist.assign(SO2=None, NO2=None, O3=None, CO=None), est)
    for r in res["estaciones"]:
        fila = nuevo[nuevo.estacion == r["estacion"]].iloc[0]
        r["aqi"] = {"PM2.5": fila.aqi_pm25, "PM10": fila.aqi_pm10}
    res["fuente"] = "SENAMHI (estaciones oficiales) vía World Air Quality Index – aqicn.org"
    res["nota"] = ("Concentraciones aproximadas: WAQI publica índices AQI (US EPA) y aquí se convierten a µg/m³. "
                   "Los promedios de 24 h se calculan con el historial horario que acumula este observatorio.")
    (salida / "aire.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":"), default=str))
    return {"ok": True, "ultimo_dato": res["resumen"]["ultimo_dato"], "registros": int(len(nuevo)), "via": "WAQI"}


def ejecutar(salida: Path, archivo: Path, entrada: Path | None = None, token: str | None = None) -> dict:
    if entrada is None:
        try:
            texto = requests.get(URL, headers=H, timeout=20).text  # funciona solo desde el Perú
        except requests.RequestException:
            if not token:
                raise RuntimeError("SENAMHI inaccesible desde este servidor y falta WAQI_TOKEN")
            return ejecutar_waqi(salida, archivo, token)
    else:
        texto = entrada.read_text()
    df, est = parsear(texto)
    if df.empty:
        raise RuntimeError("SENAMHI no devolvió mediciones")
    res = indicadores(df, est)
    (salida / "aire.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    archivo.mkdir(parents=True, exist_ok=True)
    df = df.assign(fecha_hora=df.fecha_hora.dt.strftime("%Y-%m-%d %H:%M"))
    for dia, parte in df.groupby(df.fecha_hora.str[:10]):
        f = archivo / "aire" / dia[:7] / f"aire_{dia}.csv"
        f.parent.mkdir(parents=True, exist_ok=True)
        if f.exists():
            parte = pd.concat([pd.read_csv(f), parte], ignore_index=True)
        parte.drop_duplicates(subset=["estacion", "fecha_hora"], keep="last").sort_values(["fecha_hora", "estacion"]).to_csv(f, index=False)
    return {"ok": True, "ultimo_dato": res["resumen"]["ultimo_dato"], "registros": int(len(df)), "via": "SENAMHI directo"}
