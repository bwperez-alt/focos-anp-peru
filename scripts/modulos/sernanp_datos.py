"""Datos abiertos del SERNANP (Plataforma Nacional de Datos Abiertos).

- Frecuencia de visitas turísticas en las ANP (mensual, por sector, procedencia y edad)
  https://www.datosabiertos.gob.pe/dataset/frecuencia-de-visitas-tur%C3%ADsticas-en-las-%C3%A1reas-naturales-protegidas-por-el-estado-%E2%80%93-servicio
- Registro de monitoreo de la deforestación en el ámbito de las ANP (ha por año, mes, causa, tipo de bosque, zona)
  https://www.datosabiertos.gob.pe/dataset/registro-de-monitoreo-de-la-deforestaci%C3%B3n-en-el-%C3%A1mbito-de-las-%C3%A1reas-naturales-protegidas-%E2%80%93

Se descargan una vez al día como máximo (los conjuntos se actualizan pocas veces al año).
"""
from __future__ import annotations

import io
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HOY = lambda: pd.Timestamp.now(tz="America/Lima").tz_localize(None).to_period("M")

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
URL_VISITAS = "https://www.datosabiertos.gob.pe/sites/default/files/SERNANPdataset_Turismo.csv"
URL_DEFO = "https://www.datosabiertos.gob.pe/sites/default/files/Dataset_DeforestacionAnp_SERNANP.csv"
WEB_VISITAS = "https://www.datosabiertos.gob.pe/dataset/frecuencia-de-visitas-tur%C3%ADsticas-en-las-%C3%A1reas-naturales-protegidas-por-el-estado-%E2%80%93-servicio"
WEB_DEFO = "https://www.datosabiertos.gob.pe/dataset/registro-de-monitoreo-de-la-deforestaci%C3%B3n-en-el-%C3%A1mbito-de-las-%C3%A1reas-naturales-protegidas-%E2%80%93"

SIGLAS = {"BP": "bosque de proteccion", "PN": "parque nacional", "RN": "reserva nacional", "RC": "reserva comunal",
          "RP": "reserva paisajistica", "RVS": "refugio de vida silvestre", "SH": "santuario historico",
          "SN": "santuario nacional", "ZR": "zona reservada", "CC": "coto de caza"}
VACIAS = {"de", "del", "la", "las", "los", "y", "el"}
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]


def clave(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return " ".join(w for w in t.split() if w not in VACIAS)


def emparejar(nombres_oficiales: list[str]):
    """Devuelve una función que busca el nombre oficial completo a partir de categoría + nombre."""
    idx = {clave(n): n for n in nombres_oficiales}
    solo_nombre = {}
    for n in nombres_oficiales:
        for cat in SIGLAS.values():
            k = clave(n)
            if k.startswith(cat + " "):
                solo_nombre.setdefault(k[len(cat) + 1:], []).append(n)

    def buscar(categoria: str, nombre: str) -> str | None:
        k = clave(f"{categoria} {nombre}")
        if k in idx:
            return idx[k]
        cands = solo_nombre.get(clave(nombre), [])
        return cands[0] if len(cands) == 1 else None
    return buscar


def leer_csv(url: str, entrada: Path | None) -> pd.DataFrame:
    contenido = entrada.read_bytes() if entrada else requests.get(url, headers=H, timeout=90).content
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(io.StringIO(contenido.decode(enc)))
        except UnicodeDecodeError:
            continue
    raise RuntimeError("No se pudo leer " + url)


def serie_hasta_hoy(mensual: pd.Series, hoy: pd.Period, g_ref: float | None = None) -> tuple[list[dict], float]:
    """Serie mensual desde el primer mes oficial hasta el mes actual.

    Meses con dato del SERNANP -> 'oficial'. Meses sin dato publicado -> 'estimado':
    promedio del mismo mes calendario en los años oficiales x tendencia anual observada
    (cociente entre años en los meses comunes, acotado a 0,85–1,25), elevada a la distancia en años.
    """
    if mensual.empty:
        return [], 1.0
    porm = mensual.groupby(mensual.index.month)
    base = porm.mean()
    anio_base = mensual.groupby(mensual.index.month).apply(lambda x: float(np.mean([p.year for p in x.index])))
    anios = sorted(set(mensual.index.year))
    g = 1.0
    if len(anios) >= 2:
        a0, a1 = anios[-2], anios[-1]
        comunes = [m for m in range(1, 13) if pd.Period(f"{a0}-{m:02d}") in mensual.index and pd.Period(f"{a1}-{m:02d}") in mensual.index]
        s0 = sum(mensual[pd.Period(f"{a0}-{m:02d}")] for m in comunes); s1 = sum(mensual[pd.Period(f"{a1}-{m:02d}")] for m in comunes)
        if comunes and s0 > 0:
            g = float(np.clip(s1 / s0, 0.85, 1.25))
    if g_ref is not None:  # por ANP: se modera hacia la tendencia nacional para evitar extrapolar picos aislados
        g = float(np.clip((g + g_ref) / 2, 0.90, 1.15))
    out = []
    for per in pd.period_range(mensual.index.min(), hoy, freq="M"):
        if per in mensual.index:
            out.append({"mes": str(per), "v": int(mensual[per]), "tipo": "oficial"})
        elif per.month in base.index:
            out.append({"mes": str(per), "v": int(round(base[per.month] * g ** (per.year - anio_base[per.month]))), "tipo": "estimado"})
        else:
            out.append({"mes": str(per), "v": None, "tipo": "sin dato"})
    return out, g


def visitas(df: pd.DataFrame, buscar) -> dict:
    df = df.copy()
    df["visitas"] = df[["VISITAS_E1", "VISITAS_E2A3", "VISITAS_E3A30"]].sum(axis=1)
    df["fecha"] = pd.to_datetime(df.FECHA.astype(str), format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["fecha"])
    df["mes"] = df.fecha.dt.month
    sig = df.ANP.str.extract(r"^([A-Z]+)\s+(.*)$")
    df["area"] = [buscar(SIGLAS.get(a, ""), b) or f"{SIGLAS.get(a, a).title()} {b}" for a, b in zip(sig[0], sig[1])]
    meses_cubiertos = df.fecha.dt.to_period("M").nunique()
    _, g_nac = serie_hasta_hoy(df.groupby(df.fecha.dt.to_period("M")).visitas.sum(), HOY())
    areas = {}
    for area, g in df.groupby("area"):
        mensual = g.groupby(g.fecha.dt.to_period("M")).visitas.sum()
        perfil = mensual.groupby(mensual.index.month).mean().reindex(range(1, 13)).fillna(0)
        total = g.visitas.sum()
        proc = g.groupby("PROCEDENCIA").visitas.sum()
        top3 = list(perfil.sort_values(ascending=False).index[:3])
        por_anio = {str(y): int(v) for y, v in mensual.groupby(mensual.index.year).sum().items()}
        serie, crec = serie_hasta_hoy(mensual, HOY(), g_nac)
        areas[area] = {
            "serie": serie, "crecimiento_anual": round(crec, 3),
            "nombre_sernanp": g.ANP.iat[0],
            "por_anio": por_anio,
            "mensual": {str(p): int(v) for p, v in mensual.items()},
            "promedio_anual": round(float(mensual.sum() / max(1, mensual.index.nunique()) * 12)),
            "perfil_mensual": [round(float(x)) for x in perfil],
            "meses_pico": [MESES[m - 1] for m in top3],
            "meses_pico_num": [int(m) for m in top3],
            "pct_extranjeros": round(100 * float(proc.get("EXTRANJERO", 0)) / total, 1) if total else None,
            "pct_nacionales": round(100 * float(proc.get("NACIONAL", 0) + proc.get("LOCAL", 0)) / total, 1) if total else None,
            "pct_pernocta": round(100 * float(g.VISITAS_E2A3.sum() + g.VISITAS_E3A30.sum()) / total, 1) if total else None,
            "sectores": sorted(g.SECTOR.dropna().unique().tolist())[:12],
        }
    nac = df.groupby(df.fecha.dt.to_period("M")).visitas.sum()
    serie_nac, crec_nac = serie_hasta_hoy(nac, HOY())
    anios = {}
    for y, g in nac.groupby(nac.index.year):
        anios[str(y)] = {"visitas": int(g.sum()), "meses": int(len(g)),
                         "desde": str(g.index.min()), "hasta": str(g.index.max()), "completo": len(g) == 12}
    return {
        "fuente": "SERNANP – Frecuencia de visitas turísticas en las ANP (Plataforma Nacional de Datos Abiertos)",
        "url": WEB_VISITAS,
        "periodo": {"desde": df.fecha.min().strftime("%Y-%m"), "hasta": df.fecha.max().strftime("%Y-%m"), "meses": int(meses_cubiertos)},
        "fecha_corte": str(df.FECHA_CORTE.max()),
        "nota": "Visitas mensuales registradas por el SERNANP. La plataforma muestra la estacionalidad típica de cada área; no es un conteo en tiempo real.",
        "serie_nacional": [{"mes": str(p), "visitas": int(v)} for p, v in nac.items()],
        "serie_hasta_hoy": serie_nac, "crecimiento_anual": round(crec_nac, 3), "mes_actual": str(HOY()),
        "metodo_estimacion": ("Meses sin dato publicado: promedio del mismo mes en los años oficiales × tendencia anual observada "
                              "entre los dos últimos años oficiales (nacional acotada a −15 %/+25 %; por ANP se promedia con la nacional y se acota a −10 %/+15 %). Se reemplaza por el dato oficial cuando el SERNANP lo publica."),
        "anios": anios,
        "ranking": sorted(({"area": a, "promedio_anual": v["promedio_anual"]} for a, v in areas.items()), key=lambda r: -r["promedio_anual"]),
        "areas": areas,
    }


def deforestacion(df: pd.DataFrame, buscar) -> dict:
    df = df.copy()
    cat = df.CATEGORIA.str.replace("ZONAS RESERVADAS", "ZONA RESERVADA")
    df["area"] = [buscar(c, n) or f"{c.title()} {n.title()}" for c, n in zip(cat, df.ANP)]
    df["DEFO_CAUSA"] = df.DEFO_CAUSA.str.capitalize()
    anios = sorted(df.ANIO_REPORTE.unique().tolist())
    areas = {}
    for area, g in df.groupby("area"):
        areas[area] = {
            "ha_por_anio": {str(a): round(float(g[g.ANIO_REPORTE == a].AREA_DEFO.sum()), 1) for a in anios},
            "ha_total": round(float(g.AREA_DEFO.sum()), 1),
            "causas_por_anio": {str(a): {k: round(float(v), 1) for k, v in g[g.ANIO_REPORTE == a].groupby("DEFO_CAUSA").AREA_DEFO.sum().items()} for a in anios},
            "causas": {k: round(float(v), 1) for k, v in g.groupby("DEFO_CAUSA").AREA_DEFO.sum().sort_values(ascending=False).items()},
            "tipo_bosque": {k.capitalize(): round(float(v), 1) for k, v in g.groupby("TIPO_BOSQUE").AREA_DEFO.sum().items()},
            "zonas": {k.capitalize(): round(float(v), 1) for k, v in g.groupby("ZONIFI_ANP").AREA_DEFO.sum().sort_values(ascending=False).head(4).items()},
        }
    return {
        "fuente": "SERNANP – Registro de monitoreo de la deforestación en el ámbito de las ANP (Plataforma Nacional de Datos Abiertos)",
        "url": WEB_DEFO,
        "anios": anios,
        "fecha_corte": str(df.FECHA_CORTE.max()),
        "totales": {"ha_total": round(float(df.AREA_DEFO.sum()), 1), "n_areas": int(df.area.nunique()),
                    "ha_por_anio": {str(a): round(float(df[df.ANIO_REPORTE == a].AREA_DEFO.sum()), 1) for a in anios},
                    "causas": {k: round(float(v), 1) for k, v in df.groupby("DEFO_CAUSA").AREA_DEFO.sum().sort_values(ascending=False).items()},
                    "causas_por_anio": {str(a): {k: round(float(v), 1) for k, v in df[df.ANIO_REPORTE == a].groupby("DEFO_CAUSA").AREA_DEFO.sum().sort_values(ascending=False).items()} for a in anios}},
        "ranking": sorted(({"area": a, "ha_total": v["ha_total"], "causa_principal": next(iter(v["causas"]), None)} for a, v in areas.items()),
                          key=lambda r: -r["ha_total"]),
        "areas": areas,
    }


def ejecutar(salida: Path, archivo: Path, capas_anp, entradas: tuple[Path, Path] | None = None) -> dict:
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    previo = salida / "visitas.json"
    if entradas is None and previo.exists() and (salida / "defo_sernanp.json").exists():
        try:
            prev = json.loads(previo.read_text())
            # se recalcula al cambiar de mes (la serie llega hasta el mes actual) o de versión del formato
            if prev.get("descargado", "")[:10] == hoy and prev.get("version") == 2 and prev.get("mes_actual") == str(HOY()):
                return {"omitido": True, "ultimo_dato": prev.get("periodo", {}).get("hasta")}
        except Exception:  # noqa: BLE001
            pass
    nombres = [it["nombre"] for _, c in capas_anp for it in c.items]
    buscar = emparejar(nombres)
    dv = leer_csv(URL_VISITAS, entradas[0] if entradas else None)
    dd = leer_csv(URL_DEFO, entradas[1] if entradas else None)
    rv, rd = visitas(dv, buscar), deforestacion(dd, buscar)
    rv["descargado"] = rd["descargado"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
    rv["version"] = rd["version"] = 2
    (salida / "visitas.json").write_text(json.dumps(rv, ensure_ascii=False, separators=(",", ":")))
    (salida / "defo_sernanp.json").write_text(json.dumps(rd, ensure_ascii=False, separators=(",", ":")))
    (archivo / "sernanp").mkdir(parents=True, exist_ok=True)
    dv.to_csv(archivo / "sernanp" / "visitas_turisticas_anp.csv", index=False)
    dd.to_csv(archivo / "sernanp" / "deforestacion_anp_registro.csv", index=False)
    sin_v = [a for a in rv["areas"] if a not in nombres]
    sin_d = [a for a in rd["areas"] if a not in nombres]
    return {"ultimo_dato": rv["periodo"]["hasta"], "registros": len(dv) + len(dd),
            "sin_emparejar": (sin_v + sin_d)[:10] or None}
