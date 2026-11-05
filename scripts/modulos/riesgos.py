"""Alertas y riesgos.

- Emergencias: INDECI – COEN, reportes preliminares/complementarios y boletines (RSS oficial)
  https://portal.indeci.gob.pe/emergencias/
- Sismos: IGP – Centro Sismológico Nacional (si su servicio responde); respaldo: USGS FDSN Event Service.
"""
from __future__ import annotations

import html as htmlmod
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
BBOX = (-81.6, -18.6, -68.5, 0.2)
RSS = "https://portal.indeci.gob.pe/emergencias/feed/?paged={p}"
DISTRITOS_URL = "https://raw.githubusercontent.com/juaneladio/peru-geojson/master/peru_distrital_simple.geojson"
USGS = ("https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&minlatitude=-18.6&maxlatitude=0.2"
        "&minlongitude=-81.6&maxlongitude=-68.5&minmagnitude=3.0&starttime={desde}&orderby=time")
DIAS_SISMOS = 30
DIAS_EMERG = 15


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    return " ".join(re.sub(r"[^A-Z ]", " ", s).split())


# ------------------------------------------------------------------ distritos (centroides)
def centroides_distritos(base: Path) -> pd.DataFrame:
    f = base / "distritos_centroides.csv"
    if f.exists():
        return pd.read_csv(f)
    gj = requests.get(DISTRITOS_URL, headers=H, timeout=120).json()
    filas = []
    for ft in gj["features"]:
        p = ft.get("properties") or {}
        g = ft.get("geometry")
        if not g or not g.get("coordinates"):
            continue
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        anillo = max((np.asarray(pl[0]) for pl in polys), key=len)
        x, y = anillo[:, 0], anillo[:, 1]
        a = x[:-1] * y[1:] - x[1:] * y[:-1]
        A = a.sum() / 2 or 1e-12
        cx, cy = ((x[:-1] + x[1:]) * a).sum() / (6 * A), ((y[:-1] + y[1:]) * a).sum() / (6 * A)
        filas.append({"departamento": norm(p.get("NOMBDEP", "")), "provincia": norm(p.get("NOMBPROV", "")),
                      "distrito": norm(p.get("NOMBDIST", "")), "lon": round(float(cx), 4), "lat": round(float(cy), 4)})
    df = pd.DataFrame(filas)
    df.to_csv(f, index=False)
    return df


# ------------------------------------------------------------------ emergencias INDECI
def parsear_titulo(t: str) -> dict:
    t = htmlmod.unescape(re.sub(r"\s+", " ", t)).strip()
    out = {"titulo": t, "documento": None, "tipo": None, "distrito": None, "departamento": None}
    m = re.match(r"^(REPORTE (?:PRELIMINAR|COMPLEMENTARIO|DE PELIGRO INMINENTE)|BOLET[IÍ]N INFORMATIVO)", t, re.I)
    out["documento"] = m.group(1).capitalize() if m else None
    resto = re.split(r"HORAS\s*(?:\([^)]*\))?\s*", t, maxsplit=1)
    resto = resto[1] if len(resto) > 1 else t
    d = re.search(r"\s+EN EL DISTRITO DE\s+(.+?)\s*[–-]\s*([^–-]+)$", resto, re.I)
    if d:
        out["tipo"] = resto[: d.start()].strip(" -–").capitalize()
        out["distrito"], out["departamento"] = d.group(1).strip().title(), d.group(2).strip().title()
    else:
        dep = re.search(r"\s+EN (?:EL DEPARTAMENTO|LA REGI[OÓ]N) DE\s+(.+)$", resto, re.I)
        if dep:
            out["tipo"] = resto[: dep.start()].strip(" -–").capitalize()
            out["departamento"] = dep.group(1).strip(" .").title()
        elif out["documento"] and out["documento"].lower().startswith("bolet"):
            b = re.search(r"ANTE\s+(.+?)\s+N\s*[°º]", t, re.I)
            out["tipo"] = ("Aviso: " + b.group(1).lower()) if b else "Boletín de aviso"
    return out


def emergencias_indeci(base: Path) -> list[dict]:
    items, limite = [], datetime.now(timezone.utc) - timedelta(days=DIAS_EMERG)
    for p in range(1, 16):
        r = requests.get(RSS.format(p=p), headers=H, timeout=60)
        if r.status_code != 200:
            break
        root = ET.fromstring(r.content)
        nuevos = root.findall("./channel/item")
        if not nuevos:
            break
        viejo = False
        for it in nuevos:
            fecha = pd.to_datetime(it.findtext("pubDate"), utc=True, errors="coerce")
            if pd.isna(fecha) or fecha < limite:
                viejo = True
                continue
            info = parsear_titulo(it.findtext("title") or "")
            info.update({"publicado": fecha.tz_convert("America/Lima").strftime("%Y-%m-%d %H:%M"), "url": it.findtext("link")})
            items.append(info)
        if viejo:
            break
    # ubicación aproximada: centroide del distrito (INEI)
    try:
        cen = centroides_distritos(base)
        idx = {(r.departamento, r.distrito): (r.lon, r.lat) for r in cen.itertuples()}
        for it in items:
            if it["distrito"] and it["departamento"]:
                k = (norm(it["departamento"]), norm(it["distrito"]))
                if k in idx:
                    it["lon"], it["lat"] = idx[k]
    except Exception as e:  # noqa: BLE001
        print("  (sin centroides de distritos)", e)
    # Una entrada por emergencia (el último reporte de cada distrito/tipo)
    vistos, unicos = set(), []
    for it in items:
        clave = (it["tipo"], it["distrito"], it["departamento"]) if it["distrito"] else (it["titulo"],)
        if clave in vistos:
            continue
        vistos.add(clave)
        unicos.append(it)
    return unicos


# ------------------------------------------------------------------ sismos
def sismos_usgs() -> pd.DataFrame:
    desde = (datetime.now(timezone.utc) - timedelta(days=DIAS_SISMOS)).strftime("%Y-%m-%d")
    d = requests.get(USGS.format(desde=desde), headers=H, timeout=60).json()
    return pd.DataFrame([{
        "t": pd.to_datetime(f["properties"]["time"], unit="ms", utc=True), "lon": f["geometry"]["coordinates"][0],
        "lat": f["geometry"]["coordinates"][1], "prof_km": f["geometry"]["coordinates"][2], "mag": f["properties"]["mag"],
        "ref": f["properties"].get("place") or "", "url": f["properties"].get("url"), "fuente": "USGS"} for f in d["features"]])


def anp_cercana(capas_anp, lon, lat):
    cent = []
    for _, c in capas_anp[:2]:
        for it in c.items:
            lo = np.mean([(p[2][0] + p[3][0]) / 2 for p in it["partes"]])
            la = np.mean([(p[2][1] + p[3][1]) / 2 for p in it["partes"]])
            cent.append((it["nombre"], lo, la))
    nombres = [c[0] for c in cent]
    cx = np.array([c[1] for c in cent]); cy = np.array([c[2] for c in cent])
    d = np.hypot((cx - lon) * 111.32 * np.cos(np.radians(lat)), (cy - lat) * 110.57)
    i = int(np.argmin(d))
    return nombres[i], round(float(d[i]))


def ejecutar(salida: Path, archivo: Path, capas_anp, capa_za, base: Path | None = None) -> dict:
    base = base or Path(__file__).resolve().parents[2] / "data" / "base"
    errores = {}
    try:
        emerg = emergencias_indeci(base)
    except Exception as e:  # noqa: BLE001
        emerg, errores["indeci"] = [], f"{type(e).__name__}: {e}"[:200]
    # cruzar emergencias con ANP / ZA (centroide del distrito)
    for it in emerg:
        if "lon" in it:
            xy = np.array([[it["lon"], it["lat"]]])
            it["zona"], it["area"] = "Fuera de ANP", ""
            for _, c in capas_anp:
                k = c.asignar(xy)[0]
                if k >= 0:
                    it["zona"], it["area"] = "Dentro de ANP", c.items[k]["nombre"]
                    break
            else:
                k = capa_za.asignar(xy)[0]
                if k >= 0:
                    it["zona"], it["area"] = "Zona de amortiguamiento", capa_za.items[k]["nombre"]

    try:
        df = sismos_usgs()
        x0, y0, x1, y1 = BBOX
        df = df[df.lon.between(x0, x1) & df.lat.between(y0, y1)].sort_values("t", ascending=False)
    except Exception as e:  # noqa: BLE001
        df, errores["sismos"] = pd.DataFrame(), f"{type(e).__name__}: {e}"[:200]
    sismos = []
    for r in df.itertuples():
        nom, km = anp_cercana(capas_anp, r.lon, r.lat)
        sismos.append({"t": r.t.tz_convert("America/Lima").strftime("%Y-%m-%d %H:%M"), "lat": round(r.lat, 3), "lon": round(r.lon, 3),
                       "mag": r.mag, "prof_km": None if pd.isna(r.prof_km) else round(float(r.prof_km)), "ref": r.ref,
                       "anp_cercana": nom, "dist_anp_km": km, "url": r.url, "fuente": r.fuente})

    tipos = pd.Series([e["tipo"] or "Otro" for e in emerg]).value_counts().head(10).to_dict() if emerg else {}
    res = {
        "fuentes": {"emergencias": "INDECI – COEN", "sismos": "USGS (respaldo: el servicio de datos del IGP no está disponible públicamente)"},
        "emergencias": emerg,
        "resumen_emergencias": {"n": len(emerg), "dias": DIAS_EMERG, "por_tipo": tipos,
                                "incendios_forestales": sum(1 for e in emerg if (e["tipo"] or "").lower().startswith("incendio forestal")),
                                "en_anp_o_za": sum(1 for e in emerg if e.get("zona") in ("Dentro de ANP", "Zona de amortiguamiento"))},
        "sismos": sismos,
        "resumen_sismos": {"n": len(sismos), "dias": DIAS_SISMOS, "n_m45": sum(1 for s in sismos if s["mag"] >= 4.5),
                           "mayor": max(sismos, key=lambda s: s["mag"]) if sismos else None},
        "errores": errores,
    }
    (salida / "riesgos.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    archivo.mkdir(parents=True, exist_ok=True)
    for nombre, filas, claves in [("emergencias_indeci.csv", emerg, ["titulo"]), ("sismos.csv", sismos, ["t", "lat", "lon"])]:
        if not filas:
            continue
        f = archivo / nombre
        nuevo = pd.DataFrame(filas)
        if f.exists():
            nuevo = pd.concat([pd.read_csv(f), nuevo], ignore_index=True)
        nuevo.drop_duplicates(subset=claves, keep="last").to_csv(f, index=False)
    if not emerg and not sismos:
        raise RuntimeError(f"Sin datos: {errores}")
    return {"ultimo_dato": emerg[0]["publicado"] if emerg else (sismos[0]["t"] if sismos else None),
            "registros": len(emerg) + len(sismos), "errores": errores or None}
