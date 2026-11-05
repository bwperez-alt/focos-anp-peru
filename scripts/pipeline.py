"""
Focos de calor en Áreas Naturales Protegidas del Perú
=====================================================

Flujo: fuente pública (NASA FIRMS) -> limpieza -> cruce con el territorio
(SERNANP: ANP, zonas de amortiguamiento; límites departamentales) ->
indicadores para el dashboard.

Uso:
    python scripts/pipeline.py                 # descarga en vivo (últimos 7 días)
    python scripts/pipeline.py --ventana 48h   # 24h | 48h | 7d
    python scripts/pipeline.py --entrada carpeta_con_csv   # modo sin conexión

Dependencias: requests, numpy, pandas, matplotlib, scikit-learn
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from matplotlib.path import Path as MplPath
from sklearn.cluster import DBSCAN

RAIZ = Path(__file__).resolve().parents[1]
BASE = RAIZ / "data" / "base"
SALIDA = RAIZ / "docs" / "data"
ARCHIVO = RAIZ / "data" / "archivo"

# Archivos públicos de FIRMS (no requieren clave). Solo VIIRS: 375 m de resolución.
FIRMS = "https://firms.modaps.eosdis.nasa.gov/data/active_fire"
SENSORES = {
    "VIIRS S-NPP": "suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_South_America_{v}.csv",
    "VIIRS NOAA-20": "noaa-20-viirs-c2/csv/J1_VIIRS_C2_South_America_{v}.csv",
    "VIIRS NOAA-21": "noaa-21-viirs-c2/csv/J2_VIIRS_C2_South_America_{v}.csv",
}
ARCHIVO_LOCAL = {"VIIRS S-NPP": "snpp.csv", "VIIRS NOAA-20": "n20.csv", "VIIRS NOAA-21": "n21.csv"}

BBOX_PERU = (-81.6, -18.6, -68.5, 0.2)  # lon_min, lat_min, lon_max, lat_max
EPS_KM = 1.0          # distancia para agrupar focos en un mismo evento
KM_POR_DIA = 1.0      # 1 día de diferencia "pesa" como 1 km al agrupar
DIAS_PERSISTENTE = 4  # celda con focos en >= N días distintos -> fuente persistente (no incendio)
CELDA_GRADOS = 0.004  # ~400 m, tamaño de celda para detectar fuentes persistentes


# --------------------------------------------------------------------------- #
# 1. Captura
# --------------------------------------------------------------------------- #
def capturar(ventana: str, entrada: Path | None) -> pd.DataFrame:
    tablas = []
    for sensor, ruta in SENSORES.items():
        try:
            if entrada:
                texto = (entrada / ARCHIVO_LOCAL[sensor]).read_text()
            else:
                r = requests.get(f"{FIRMS}/{ruta.format(v=ventana)}", timeout=60)
                r.raise_for_status()
                texto = r.text
            df = pd.read_csv(io.StringIO(texto))
            df["sensor"] = sensor
            tablas.append(df)
            print(f"  {sensor}: {len(df):,} detecciones (Sudamérica)")
        except Exception as e:  # un sensor caído no debe tumbar todo el flujo
            print(f"  ! {sensor}: no disponible ({e})", file=sys.stderr)
    if not tablas:
        raise RuntimeError("No se pudo descargar ningún sensor de FIRMS.")
    return pd.concat(tablas, ignore_index=True)


# --------------------------------------------------------------------------- #
# Geometría (sin GDAL: punto-en-polígono con matplotlib)
# --------------------------------------------------------------------------- #
class Capa:
    """Polígonos GeoJSON con prueba rápida de punto-en-polígono (respeta huecos)."""

    def __init__(self, archivo: Path, nombre, extra=None):
        gj = json.loads(archivo.read_text())
        self.items = []
        for f in gj["features"]:
            geom = f.get("geometry")
            if not geom:
                continue
            polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
            partes = []
            for p in polys:
                ext = np.asarray(p[0])
                huecos = [MplPath(np.asarray(h)) for h in p[1:]]
                partes.append((MplPath(ext), huecos, ext.min(0), ext.max(0)))
            props = f["properties"]
            self.items.append({
                "nombre": nombre(props) if callable(nombre) else props.get(nombre, ""),
                "extra": extra(props) if extra else {},
                "partes": partes,
            })

    def asignar(self, xy: np.ndarray) -> np.ndarray:
        """Índice del primer polígono que contiene cada punto (-1 si ninguno)."""
        idx = np.full(len(xy), -1)
        for i, it in enumerate(self.items):
            libres = idx == -1
            if not libres.any():
                break
            for ruta, huecos, lo, hi in it["partes"]:
                cand = libres & (xy[:, 0] >= lo[0]) & (xy[:, 0] <= hi[0]) & (xy[:, 1] >= lo[1]) & (xy[:, 1] <= hi[1])
                if not cand.any():
                    continue
                pts = xy[cand]
                dentro = ruta.contains_points(pts)
                for h in huecos:
                    dentro &= ~h.contains_points(pts)
                pos = np.flatnonzero(cand)[dentro]
                idx[pos] = i
                libres[pos] = False
        return idx


def titulo(s: str) -> str:
    s = (s or "").strip()
    if s.isupper():
        s = s.title().replace(" De ", " de ").replace(" Del ", " del ")
    return s


# --------------------------------------------------------------------------- #
# 2. Limpieza
# --------------------------------------------------------------------------- #
def limpiar(df: pd.DataFrame, deps: Capa) -> tuple[pd.DataFrame, dict]:
    bit = {"brutos_sudamerica": int(len(df))}

    # a) recorte rápido por caja y luego por el contorno real del Perú
    x0, y0, x1, y1 = BBOX_PERU
    df = df[df.longitude.between(x0, x1) & df.latitude.between(y0, y1)].copy()
    xy = df[["longitude", "latitude"]].to_numpy()
    idep = deps.asignar(xy)
    df["departamento"] = [titulo(deps.items[i]["nombre"]) if i >= 0 else None for i in idep]
    df = df[df.departamento.notna()]
    bit["en_peru"] = int(len(df))

    # b) confianza: se descartan las detecciones de confianza baja
    conf = df.confidence.astype(str).str.lower().str[0].map({"l": "baja", "n": "nominal", "h": "alta"})
    df["confianza"] = conf.fillna("nominal")
    df = df[df.confianza != "baja"]
    bit["sin_baja_confianza"] = int(len(df))

    # c) duplicados exactos (mismo sensor, lugar y hora)
    df = df.drop_duplicates(subset=["sensor", "latitude", "longitude", "acq_date", "acq_time"])
    bit["sin_duplicados"] = int(len(df))

    # d) fuentes persistentes (antorchas de gas, industrias, volcanes): misma celda en muchos días
    df["celda"] = (np.floor(df.latitude / CELDA_GRADOS).astype(int).astype(str) + "_" +
                   np.floor(df.longitude / CELDA_GRADOS).astype(int).astype(str))
    dias = df.groupby("celda").acq_date.nunique()
    persist = set(dias[dias >= DIAS_PERSISTENTE].index)
    df["persistente"] = df.celda.isin(persist)
    bit["fuentes_persistentes"] = int(df.persistente.sum())
    df = df[~df.persistente].drop(columns=["celda", "persistente"])
    bit["focos_validos"] = int(len(df))

    # fecha/hora (UTC) -> hora Perú
    t = pd.to_datetime(df.acq_date + " " + df.acq_time.astype(str).str.zfill(4), format="%Y-%m-%d %H%M", utc=True)
    df["fecha_hora_pe"] = t.dt.tz_convert("America/Lima")
    df["fecha"] = df.fecha_hora_pe.dt.strftime("%Y-%m-%d")
    return df.reset_index(drop=True), bit


# --------------------------------------------------------------------------- #
# 3. Eventos: focos cercanos en espacio y tiempo = un mismo incendio
# --------------------------------------------------------------------------- #
def agrupar_eventos(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        df["evento"] = []
        return df
    lat0 = np.radians(-9.0)
    x = df.longitude.to_numpy() * 111.32 * np.cos(lat0)
    y = df.latitude.to_numpy() * 110.57
    dias = (df.fecha_hora_pe - df.fecha_hora_pe.min()).dt.total_seconds().to_numpy() / 86400
    X = np.column_stack([x, y, dias * KM_POR_DIA])
    df["evento"] = DBSCAN(eps=EPS_KM, min_samples=1).fit_predict(X)
    return df


# --------------------------------------------------------------------------- #
# 4. Cruce con el territorio
# --------------------------------------------------------------------------- #
def cruzar(df: pd.DataFrame) -> pd.DataFrame:
    capas_anp, za = capas_territorio()
    xy = df[["longitude", "latitude"]].to_numpy()
    df["zona"] = "Fuera de ANP"
    df["area"] = ""
    df["categoria"] = ""
    libre = np.ones(len(df), bool)
    for tipo, capa in capas_anp:
        idx = np.full(len(df), -1)
        idx[libre] = capa.asignar(xy[libre])
        hit = idx >= 0
        df.loc[hit, "zona"] = "Dentro de ANP"
        df.loc[hit, "area"] = [capa.items[i]["nombre"] for i in idx[hit]]
        df.loc[hit, "categoria"] = [capa.items[i]["extra"].get("cat") or tipo for i in idx[hit]]
        libre &= ~hit
    idx = np.full(len(df), -1)
    idx[libre] = za.asignar(xy[libre])
    hit = idx >= 0
    df.loc[hit, "zona"] = "Zona de amortiguamiento"
    df.loc[hit, "area"] = [za.items[i]["nombre"] for i in idx[hit]]
    df.loc[hit, "categoria"] = "Zona de amortiguamiento"
    return df


# --------------------------------------------------------------------------- #
# 5. Indicadores y salidas
# --------------------------------------------------------------------------- #
def indicadores(df: pd.DataFrame, limpieza: dict, ventana: str) -> dict:
    n = len(df)
    ev = df.groupby("evento").agg(zona=("zona", lambda s: s.mode().iat[0])) if n else pd.DataFrame(columns=["zona"])

    def por_zona(z):
        return {"focos": int((df.zona == z).sum()), "eventos": int((ev.zona == z).sum())}

    rank = (df[df.zona != "Fuera de ANP"]
            .groupby(["area", "categoria", "zona"])
            .agg(focos=("evento", "size"), eventos=("evento", "nunique"),
                 frp_total=("frp", "sum"), departamentos=("departamento", lambda s: ", ".join(sorted(s.unique()))),
                 ultimo=("fecha_hora_pe", "max"))
            .reset_index().sort_values(["focos", "frp_total"], ascending=False))
    rank["frp_total"] = rank.frp_total.round(1)
    rank["ultimo"] = rank.ultimo.dt.strftime("%Y-%m-%d %H:%M")

    dep = (df.groupby("departamento")
           .agg(focos=("evento", "size"), eventos=("evento", "nunique"),
                en_anp=("zona", lambda s: int((s == "Dentro de ANP").sum())),
                en_za=("zona", lambda s: int((s == "Zona de amortiguamiento").sum())))
           .reset_index().sort_values("focos", ascending=False))

    dia = (df.groupby(["fecha", "zona"]).size().unstack(fill_value=0)
           .reindex(columns=["Dentro de ANP", "Zona de amortiguamiento", "Fuera de ANP"], fill_value=0)
           .reset_index())

    fechas = df.fecha_hora_pe
    return {
        "actualizado": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "ventana": ventana,
        "periodo": {"desde": fechas.min().strftime("%Y-%m-%d %H:%M") if n else None,
                    "hasta": fechas.max().strftime("%Y-%m-%d %H:%M") if n else None},
        "limpieza": limpieza,
        "totales": {
            "focos": n, "eventos": int(df.evento.nunique()) if n else 0,
            "dentro_anp": por_zona("Dentro de ANP"),
            "zona_amortiguamiento": por_zona("Zona de amortiguamiento"),
            "fuera_anp": por_zona("Fuera de ANP"),
            "areas_afectadas": int(rank[rank.zona == "Dentro de ANP"].area.nunique()),
            "pct_en_anp_o_za": round(100 * (df.zona != "Fuera de ANP").mean(), 1) if n else 0,
        },
        "ranking_areas": rank.to_dict("records"),
        "departamentos": dep.to_dict("records"),
        "serie_diaria": dia.rename(columns={"Dentro de ANP": "anp", "Zona de amortiguamiento": "za", "Fuera de ANP": "fuera"}).to_dict("records"),
        "parametros": {"eps_km": EPS_KM, "km_por_dia": KM_POR_DIA, "dias_persistente": DIAS_PERSISTENTE,
                       "celda_grados": CELDA_GRADOS, "sensores": list(SENSORES)},
    }


def guardar(df: pd.DataFrame, res: dict) -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    # capas del SERNANP que el mapa dibuja
    (SALIDA / "capas").mkdir(exist_ok=True)
    for nombre in ["anp_nacional", "zonas_reservadas", "acr", "acp", "zonas_amortiguamiento"]:
        (SALIDA / "capas" / f"{nombre}.geojson").write_bytes((BASE / f"{nombre}.geojson").read_bytes())
    feats = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [round(r.longitude, 4), round(r.latitude, 4)]},
        "properties": {
            "f": r.fecha_hora_pe.strftime("%Y-%m-%d %H:%M"), "s": r.sensor.replace("VIIRS ", ""),
            "frp": round(float(r.frp), 1), "c": r.confianza, "z": r.zona, "a": r.area,
            "d": r.departamento, "e": int(r.evento), "dn": r.daynight,
        },
    } for r in df.itertuples()]
    (SALIDA / "focos.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")))
    (SALIDA / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))

    # Archivo histórico (para investigación): se acumula mes a mes sin duplicar
    ARCHIVO.mkdir(parents=True, exist_ok=True)
    cols = ["acq_date", "acq_time", "latitude", "longitude", "sensor", "frp", "confianza", "daynight", "departamento", "zona", "area", "categoria"]
    nuevo = df[cols].copy()
    for dia, parte in nuevo.groupby(nuevo.acq_date.str[:10]):
        f = ARCHIVO / "focos" / dia[:7] / f"focos_{dia}.csv"
        f.parent.mkdir(parents=True, exist_ok=True)
        if f.exists():
            parte = pd.concat([pd.read_csv(f), parte], ignore_index=True)
        parte.drop_duplicates(subset=["sensor", "latitude", "longitude", "acq_date", "acq_time"]).sort_values(["acq_date", "acq_time"]).to_csv(f, index=False)

    # Historial de indicadores por corrida
    h = ARCHIVO / "historial_indicadores.csv"
    t = res["totales"]
    fila = pd.DataFrame([{"actualizado": res["actualizado"], "ventana": res["ventana"], "focos": t["focos"], "eventos": t["eventos"],
                          "focos_anp": t["dentro_anp"]["focos"], "focos_za": t["zona_amortiguamiento"]["focos"],
                          "areas_afectadas": t["areas_afectadas"]}])
    fila.to_csv(h, mode="a", header=not h.exists(), index=False)


def nombre_oficial(cat: str, nomb: str) -> str:
    """'Parque Nacional' + 'del Manu' -> 'Parque Nacional del Manu'."""
    cat, nomb = (cat or "").strip(), (nomb or "").strip()
    return f"{cat} {nomb}".strip() if cat and not nomb.lower().startswith(cat.lower()) else nomb


def capas_territorio():
    """ANP (nacional, ZR, ACR, ACP) y zonas de amortiguamiento, con nombres oficiales completos."""
    anp = json.loads((BASE / "anp_nacional.geojson").read_text())
    completo = {f["properties"].get("anp_codi"): nombre_oficial(f["properties"].get("anp_cate"), f["properties"].get("anp_nomb"))
                for f in anp["features"]}
    zr = {f["properties"].get("zr_codi"): f["properties"].get("zr_nomb") for f in json.loads((BASE / "zonas_reservadas.geojson").read_text())["features"]}
    capas = [
        ("ANP nacional", Capa(BASE / "anp_nacional.geojson", lambda p: nombre_oficial(p.get("anp_cate"), p.get("anp_nomb")),
                              lambda p: {"cat": p.get("anp_cate", ""), "codi": p.get("anp_codi", ""), "ubpo": p.get("anp_ubpo", "")})),
        ("Zona reservada", Capa(BASE / "zonas_reservadas.geojson", lambda p: nombre_oficial("Zona Reservada", p.get("zr_nomb")),
                                lambda p: {"cat": "Zona Reservada", "codi": p.get("zr_codi", ""), "ubpo": p.get("zr_ubpo", "")})),
        ("Área de conservación regional", Capa(BASE / "acr.geojson", lambda p: nombre_oficial("Área de Conservación Regional", p.get("acr_nomb")),
                                               lambda p: {"cat": "Área de Conservación Regional", "codi": p.get("acr_codi", "")})),
        ("Área de conservación privada", Capa(BASE / "acp.geojson", lambda p: nombre_oficial("Área de Conservación Privada", p.get("acp_nomb")),
                                              lambda p: {"cat": "Área de Conservación Privada", "codi": p.get("acp_codi", "")})),
    ]
    za = Capa(BASE / "zonas_amortiguamiento.geojson",
              lambda p: completo.get(p.get("anp_codi")) or (nombre_oficial("Zona Reservada", zr[p.get("anp_codi")]) if p.get("anp_codi") in zr else p.get("anp_nomb", "")))
    return capas, za


def ejecutar(ventana: str = "7d", entrada: Path | None = None):
    print("1) Captura FIRMS")
    df = capturar(ventana, entrada)
    print("2) Limpieza")
    deps = Capa(BASE / "departamentos.geojson", "departamento")
    df, limp = limpiar(df, deps)
    for k, v in limp.items():
        print(f"   {k:>22}: {v:,}")
    print("3) Eventos")
    df = agrupar_eventos(df)
    print("4) Cruce con ANP y zonas de amortiguamiento")
    df = cruzar(df)
    print("5) Indicadores")
    res = indicadores(df, limp, ventana)
    guardar(df, res)
    t = res["totales"]
    print(f"   focos={t['focos']:,} eventos={t['eventos']:,} | ANP={t['dentro_anp']} | ZA={t['zona_amortiguamiento']} | áreas afectadas={t['areas_afectadas']}")
    return df, res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ventana", default="7d", choices=["24h", "48h", "7d"])
    ap.add_argument("--entrada", type=Path, help="carpeta con CSV de FIRMS (modo sin conexión)")
    a = ap.parse_args()
    ejecutar(a.ventana, a.entrada)


if __name__ == "__main__":
    main()
