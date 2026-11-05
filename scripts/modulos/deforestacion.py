"""Alertas tempranas de deforestación (ATD) – Geobosques / PNCB-MINAM.

Fuente: https://geobosques.minam.gob.pe/geobosque/view/descargas.php
Archivo: "Alertas Tempranas <año> – PNCB (Puntos)" (shapefile de puntos, UTM 18S, WGS84).
Campos: Fuente (sensor), Tipo (Antrópico / Natural), Fecha (fecha de detección).
Cada punto es un píxel de pérdida de cobertura boscosa detectado por el PNCB.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

URL = "https://geobosques.minam.gob.pe/geobosque/descargas_geobosque/alerta/espaciales/Alertas_PNCB_shape_{anio}.zip"
FUENTE_WEB = "https://geobosques.minam.gob.pe/geobosque/view/descargas.php"
H = {"User-Agent": "Mozilla/5.0 (observatorio-ambiental-peru; investigacion academica)"}
CELDA = 0.05  # grados (~5,5 km) para el mapa agregado


# ----------------------------------------------------------------- lectores sin GDAL
def leer_shp_puntos(b: bytes) -> tuple[np.ndarray, np.ndarray]:
    cuerpo = np.frombuffer(b, dtype=np.uint8, offset=100)
    n = len(cuerpo) // 28
    rec = np.frombuffer(cuerpo[: n * 28].tobytes(), dtype=np.dtype([("num", ">i4"), ("len", ">i4"), ("tipo", "<i4"), ("x", "<f8"), ("y", "<f8")]))
    if not (rec["tipo"] == 1).all():
        raise ValueError("El shapefile no es de puntos simples")
    return rec["x"].copy(), rec["y"].copy()


def leer_dbf(b: bytes, campos: list[str]) -> pd.DataFrame:
    n = int.from_bytes(b[4:8], "little")
    hl = int.from_bytes(b[8:10], "little")
    rl = int.from_bytes(b[10:12], "little")
    defs, off = [], 1
    for o in range(32, hl - 1, 32):
        nombre = b[o:o + 11].split(b"\0")[0].decode("latin1")
        largo = b[o + 16]
        defs.append((nombre, off, largo))
        off += largo
    n = min(n, (len(b) - hl) // rl)
    arr = np.frombuffer(b, dtype=np.uint8, offset=hl, count=n * rl).reshape(n, rl)
    out = {}
    for nombre, o, largo in defs:
        if nombre in campos:
            col = arr[:, o:o + largo].copy().view(f"S{largo}").ravel()
            out[nombre] = pd.Series(col).str.decode("utf-8", errors="replace").str.strip()
    return pd.DataFrame(out)


def utm_a_geo(x: np.ndarray, y: np.ndarray, zona: int = 18, sur: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """UTM (WGS84) -> lon/lat en grados (fórmulas de Snyder, precisión sub-métrica)."""
    a, f, k0 = 6378137.0, 1 / 298.257223563, 0.9996
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    x = x - 500000.0
    y = y - (10000000.0 if sur else 0)
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - np.sqrt(1 - e2)) / (1 + np.sqrt(1 - e2))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1**3 / 32) * np.sin(2 * mu) + (21 * e1**2 / 16 - 55 * e1**4 / 32) * np.sin(4 * mu)
            + (151 * e1**3 / 96) * np.sin(6 * mu) + (1097 * e1**4 / 512) * np.sin(8 * mu))
    n1 = a / np.sqrt(1 - e2 * np.sin(phi1) ** 2)
    t1 = np.tan(phi1) ** 2
    c1 = ep2 * np.cos(phi1) ** 2
    r1 = a * (1 - e2) / (1 - e2 * np.sin(phi1) ** 2) ** 1.5
    d = x / (n1 * k0)
    lat = phi1 - (n1 * np.tan(phi1) / r1) * (d**2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
                                             + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720)
    lon = (d - (1 + 2 * t1 + c1) * d**3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120) / np.cos(phi1)
    lon0 = np.radians((zona - 1) * 6 - 180 + 3)
    return np.degrees(lon + lon0), np.degrees(lat)


# ----------------------------------------------------------------- procesamiento
def cargar(anio: int, entrada=None) -> tuple[pd.DataFrame, str | None]:
    modificado = None
    if isinstance(entrada, tuple):
        shp, dbf = entrada[0].read_bytes(), entrada[1].read_bytes()
    else:
        if entrada is not None:  # zip descargado a mano desde Geobosques y subido al repositorio
            contenido = Path(entrada).read_bytes()
            modificado = "subido:" + hashlib.sha1(contenido).hexdigest()[:12]
        else:
            r = requests.get(URL.format(anio=anio), headers=H, timeout=300)
            r.raise_for_status()
            modificado, contenido = r.headers.get("last-modified"), r.content
        z = zipfile.ZipFile(io.BytesIO(contenido))
        nombre = lambda ext: next(n for n in z.namelist() if n.lower().endswith(ext))
        shp, dbf = z.read(nombre(".shp")), z.read(nombre(".dbf"))
    x, y = leer_shp_puntos(shp)
    attrs = leer_dbf(dbf, ["Fuente", "Tipo", "Fecha"])
    n = min(len(x), len(attrs))
    lon, lat = utm_a_geo(x[:n], y[:n])
    df = attrs.iloc[:n].assign(lon=lon, lat=lat)
    df["Fecha"] = pd.to_datetime(df.Fecha, format="%Y%m%d", errors="coerce")
    df["Tipo"] = df.Tipo.str.replace("Antr.*", "Antrópico", regex=True)
    return df.dropna(subset=["Fecha"]), modificado


def ejecutar(salida: Path, archivo: Path, capas_anp, capa_za, entrada=None, anio: int | None = None, previo: Path | None = None) -> dict:
    anio = anio or datetime.now(timezone.utc).year
    # El archivo oficial pesa ~13 MB y cambia pocas veces al mes: solo se descarga si cambió.
    anterior = json.loads(previo.read_text()) if previo is not None and previo.exists() else {}
    if anterior and (salida / "deforestacion_rejilla.geojson").exists():
        try:
            if isinstance(entrada, Path):
                lm = "subido:" + hashlib.sha1(entrada.read_bytes()).hexdigest()[:12]
            elif entrada is None:
                lm = requests.head(URL.format(anio=anio), headers=H, timeout=30).headers.get("last-modified")
            else:
                lm = None
            if entrada is None and not lm:
                raise RuntimeError("sin acceso")
            if lm and lm == anterior.get("archivo_actualizado"):
                return {"ok": True, "omitido": True, "ultimo_dato": anterior.get("ultima_alerta")}
        except Exception:  # noqa: BLE001
            # Geobosques bloquea conexiones desde fuera del Perú: se conserva el último procesamiento
            return {"ok": True, "omitido": True, "ultimo_dato": anterior.get("ultima_alerta"),
                    "nota": "Geobosques no accesible desde la nube; se usa el último archivo procesado"}
    df, modificado = cargar(anio, entrada)
    if df.empty:
        raise RuntimeError("Archivo de alertas vacío")
    xy = df[["lon", "lat"]].to_numpy()

    # zona: dentro de ANP / zona de amortiguamiento / fuera
    zona = np.full(len(df), "Fuera de ANP", dtype=object)
    area = np.full(len(df), "", dtype=object)
    libre = np.ones(len(df), bool)
    for tipo, capa in capas_anp:
        idx = np.full(len(df), -1)
        idx[libre] = capa.asignar(xy[libre])
        hit = idx >= 0
        zona[hit] = "Dentro de ANP"
        area[hit] = [capa.items[i]["nombre"] for i in idx[hit]]
        libre &= ~hit
    idx = np.full(len(df), -1)
    idx[libre] = capa_za.asignar(xy[libre])
    hit = idx >= 0
    zona[hit] = "Zona de amortiguamiento"
    area[hit] = [capa_za.items[i]["nombre"] for i in idx[hit]]
    df["zona"], df["area"] = zona, area

    ultima = df.Fecha.max()
    reciente = df[df.Fecha > ultima - timedelta(days=90)]
    mes = df.Fecha.dt.strftime("%Y-%m")

    serie = (df.assign(mes=mes).groupby(["mes", "zona"]).size().unstack(fill_value=0)
             .reindex(columns=["Dentro de ANP", "Zona de amortiguamiento", "Fuera de ANP"], fill_value=0).reset_index())
    rank = (df[df.zona != "Fuera de ANP"].groupby(["area", "zona"])
            .agg(alertas=("Fecha", "size"), antropicas=("Tipo", lambda s: int((s == "Antrópico").sum())),
                 ultimos_90d=("Fecha", lambda s: int((s > ultima - timedelta(days=90)).sum())), ultima=("Fecha", "max"))
            .reset_index().sort_values("alertas", ascending=False))
    rank["ultima"] = rank.ultima.dt.strftime("%Y-%m-%d")

    # mapa: rejilla de los últimos 90 días
    g = reciente.assign(gx=np.floor(reciente.lon / CELDA) * CELDA + CELDA / 2, gy=np.floor(reciente.lat / CELDA) * CELDA + CELDA / 2)
    grid = g.groupby(["gx", "gy"]).agg(n=("Fecha", "size"), anp=("zona", lambda s: int((s == "Dentro de ANP").sum()))).reset_index()
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(r.gx, 3), round(r.gy, 3)]},
              "properties": {"n": int(r.n), "anp": int(r.anp)}} for r in grid.itertuples()]
    (salida / "deforestacion_rejilla.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))

    res = {
        "fuente": "PNCB – MINAM, Geobosques: Alertas Tempranas de Deforestación (puntos)",
        "url": FUENTE_WEB,
        "archivo_actualizado": modificado,
        "anio": anio,
        "ultima_alerta": ultima.strftime("%Y-%m-%d"),
        "totales": {
            "alertas_anio": int(len(df)),
            "antropicas": int((df.Tipo == "Antrópico").sum()),
            "naturales": int((df.Tipo != "Antrópico").sum()),
            "dentro_anp": int((df.zona == "Dentro de ANP").sum()),
            "zona_amortiguamiento": int((df.zona == "Zona de amortiguamiento").sum()),
            "ultimos_90d": int(len(reciente)),
            "ultimos_90d_anp_za": int((reciente.zona != "Fuera de ANP").sum()),
        },
        "serie_mensual": serie.rename(columns={"Dentro de ANP": "anp", "Zona de amortiguamiento": "za", "Fuera de ANP": "fuera"}).to_dict("records"),
        "ranking_areas": rank.head(40).to_dict("records"),
        "celda_mapa_grados": CELDA,
    }
    (salida / "deforestacion.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))

    # archivo para investigación: resumen mensual por área (el archivo completo pesa >50 MB)
    archivo.mkdir(parents=True, exist_ok=True)
    (df.assign(mes=mes).groupby(["mes", "zona", "area", "Tipo"]).size().rename("alertas").reset_index()
       .to_csv(archivo / f"deforestacion_resumen_{anio}.csv", index=False))
    return {"ok": True, "ultimo_dato": res["ultima_alerta"], "registros": int(len(df))}
