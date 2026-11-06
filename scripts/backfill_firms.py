"""Carga histórica de focos de calor VIIRS para el Perú (2020 -> hoy) desde la API de área de NASA FIRMS.

Usa el producto estándar (SP, mejor calidad) hasta donde FIRMS lo tenga procesado y el producto
casi en tiempo real (NRT) para los meses recientes. Cada mes queda en
data/archivo/focos_historico/AAAA/focos_AAAA-MM.csv.gz con el mismo esquema y las mismas banderas
de limpieza que el archivo diario (confianza, fuente persistente, zona, ANP, departamento).

Requisito: una MAP_KEY gratuita de FIRMS (https://firms.modaps.eosdis.nasa.gov/api/map_key/)
guardada como secreto FIRMS_MAP_KEY en el repositorio.

    python scripts/backfill_firms.py                       # 2020-01-01 -> hoy
    python scripts/backfill_firms.py --desde 2026-06-01    # rehace los últimos meses (reemplaza NRT por SP)

Las descargas crudas se guardan en data/tmp_firms/ (ignorado por git) para poder reanudar.
"""
from __future__ import annotations

import argparse
import gzip
import io
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import focos_hist as fh  # noqa: E402
import pipeline as fuego  # noqa: E402

API = "https://firms.modaps.eosdis.nasa.gov/api"
CACHE = fuego.RAIZ / "data" / "tmp_firms"
# sensor -> (fuente SP, fuente NRT)
FUENTES = {
    "VIIRS S-NPP": ("VIIRS_SNPP_SP", "VIIRS_SNPP_NRT"),
    "VIIRS NOAA-20": ("VIIRS_NOAA20_SP", "VIIRS_NOAA20_NRT"),
    "VIIRS NOAA-21": ("VIIRS_NOAA21_SP", "VIIRS_NOAA21_NRT"),
}
BLOQUE = 10  # días por consulta (máximo permitido por la API)


def disponibilidad(key: str) -> dict[str, tuple[date, date]]:
    r = requests.get(f"{API}/data_availability/csv/{key}/ALL", timeout=60)
    r.raise_for_status()
    t = pd.read_csv(io.StringIO(r.text))
    return {row.data_id: (date.fromisoformat(str(row.min_date)[:10]), date.fromisoformat(str(row.max_date)[:10]))
            for row in t.itertuples()}


def bajar(key: str, fuente: str, inicio: date, dias: int) -> pd.DataFrame:
    f = CACHE / fuente / f"{inicio:%Y%m%d}_{dias}.csv"
    if f.exists():
        texto = f.read_text()
    else:
        area = ",".join(str(v) for v in fuego.BBOX_PERU)
        url = f"{API}/area/csv/{key}/{fuente}/{area}/{dias}/{inicio:%Y-%m-%d}"
        for intento in range(6):
            r = requests.get(url, timeout=180)
            if r.status_code == 200 and r.text.startswith("latitude"):
                break
            if "Exceeding allowed transaction limit" in r.text or r.status_code == 429:
                print("    límite de transacciones de FIRMS: espero 10 min", flush=True)
                time.sleep(600)
                continue
            if r.status_code == 200 and not r.text.strip():
                break
            print(f"    reintento {intento + 1}: {r.status_code} {r.text[:120]}", flush=True)
            time.sleep(20 * (intento + 1))
        else:
            raise RuntimeError(f"FIRMS no respondió para {fuente} {inicio}")
        texto = r.text
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(texto)
        time.sleep(1)
    return pd.read_csv(io.StringIO(texto)) if texto.strip() else pd.DataFrame()


def descargar(key: str, desde: date, hasta: date) -> pd.DataFrame:
    disp = disponibilidad(key)
    deps = fuego.Capa(fuego.BASE / "departamentos.geojson", "departamento")
    tablas = []
    for sensor, (sp, nrt) in FUENTES.items():
        d = desde
        while d <= hasta:
            dias = min(BLOQUE, (hasta - d).days + 1)
            fin = d + timedelta(days=dias - 1)
            # SP si el bloque completo ya está procesado; si no, NRT; si ninguno cubre la fecha, se salta
            fuente = None
            if sp in disp and disp[sp][0] <= d and fin <= disp[sp][1]:
                fuente, prod = sp, "SP"
            elif nrt in disp and disp[nrt][0] <= fin:
                fuente, prod = nrt, "NRT"
            if fuente:
                df = bajar(key, fuente, d, dias)
                if not df.empty:
                    # recorte al contorno del Perú de inmediato para no acumular memoria
                    x0, y0, x1, y1 = fuego.BBOX_PERU
                    df = df[df.longitude.between(x0, x1) & df.latitude.between(y0, y1)].copy()
                    idep = deps.asignar(df[["longitude", "latitude"]].to_numpy())
                    df["departamento"] = [fuego.titulo(deps.items[i]["nombre"]) if i >= 0 else None for i in idep]
                    df = df[df.departamento.notna()]
                    df["sensor"], df["producto"] = sensor, prod
                    tablas.append(df)
                print(f"  {sensor} {d} ({prod}): {len(df):,} focos en el Perú", flush=True)
            d = fin + timedelta(days=1)
    if not tablas:
        return pd.DataFrame()
    return pd.concat(tablas, ignore_index=True)


def procesar(df: pd.DataFrame, desde: date) -> pd.DataFrame:
    df = df.drop_duplicates(subset=fh.CLAVE).copy()
    df["acq_date"] = df.acq_date.astype(str)
    conf = df.confidence.astype(str).str.lower().str[0].map({"l": "baja", "n": "nominal", "h": "alta"})
    df["confianza"] = conf.fillna("nominal")
    df["celda"] = fh.celda(df.latitude, df.longitude)
    ok = df.confianza != "baja"
    # contexto: los 40 días previos ya archivados, para que el filtro móvil no se corte en el borde
    ctx = []
    for m in {(desde - timedelta(days=40)).strftime("%Y-%m"), (desde - timedelta(days=1)).strftime("%Y-%m")}:
        f = fh.HISTORICO / m[:4] / f"focos_{m}.csv.gz"
        if f.exists():
            a = pd.read_csv(f)
            a = a[(a.confianza != "baja") & (a.acq_date < desde.isoformat())]
            ctx.append(pd.DataFrame({"celda": fh.celda(a.latitude, a.longitude), "acq_date": a.acq_date.astype(str)}))
    persist = fh.marcar_persistentes(pd.concat([df.loc[ok, ["celda", "acq_date"]], *ctx], ignore_index=True))
    df["persistente"] = [(c, d) in persist for c, d in zip(df.celda, df.acq_date)]
    df["valido"] = ok & ~df.persistente
    df = fuego.cruzar(df.drop(columns=["celda"]).reset_index(drop=True))
    return fh.normalizar(fh.con_fecha_pe(df))


def guardar(df: pd.DataFrame, desde: date, hasta: date) -> None:
    for m, parte in df.groupby(df.fecha_pe.str[:7]):
        f = fh.HISTORICO / m[:4] / f"focos_{m}.csv.gz"
        f.parent.mkdir(parents=True, exist_ok=True)
        if f.exists():  # conserva los días del mes fuera del rango rehecho
            prev = fh.normalizar(pd.read_csv(f, dtype={"area": str, "categoria": str}))
            prev = prev[(prev.acq_date < desde.isoformat()) | (prev.acq_date > hasta.isoformat())]
            parte = pd.concat([prev, parte], ignore_index=True).drop_duplicates(subset=fh.CLAVE, keep="last")
        parte = parte.sort_values(["fecha_pe", "hora_pe"])
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
            gz.write(parte.to_csv(index=False).encode())
        f.write_bytes(buf.getvalue())
        print(f"  {f.relative_to(fuego.RAIZ)}: {len(parte):,} focos ({parte.valido.sum():,} válidos)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", default="2020-01-01")
    ap.add_argument("--hasta", default=date.today().isoformat())
    ap.add_argument("--meses-atras", type=int, help="alternativa a --desde: rehace los últimos N meses")
    a = ap.parse_args()
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key:
        sys.exit("Falta FIRMS_MAP_KEY (secreto del repositorio).")
    hasta = date.fromisoformat(a.hasta)
    desde = date.fromisoformat(a.desde)
    if a.meses_atras:
        desde = (pd.Timestamp(hasta) - pd.DateOffset(months=a.meses_atras)).date().replace(day=1)
    # se procesa por años para limitar la memoria del runner
    d = desde
    while d <= hasta:
        fin = min(date(d.year, 12, 31), hasta)
        print(f"\n### {d} -> {fin}", flush=True)
        crudo = descargar(key, d, fin)
        if not crudo.empty:
            guardar(procesar(crudo, d), d, fin)
        d = fin + timedelta(days=1)


if __name__ == "__main__":
    main()
