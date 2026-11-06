"""Utilidades compartidas para el archivo de focos y la serie 2020–hoy.

- Esquema único del archivo de focos (crudo, con banderas de limpieza).
- Filtro de fuentes persistentes en ventana móvil (mismo criterio en la corrida
  horaria y en la carga histórica).
- Superficie de cada ANP (km²) para normalizar conteos.
- Serie mensual por ANP: docs/data/serie_focos.json y archivos mensuales
  docs/data/historico/focos_AAAA-MM.csv.gz para el constructor de descargas.
"""
from __future__ import annotations

import gzip
import io
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
ARCHIVO = RAIZ / "data" / "archivo"
DIARIO = ARCHIVO / "focos"                    # AAAA-MM/focos_AAAA-MM-DD.csv (día de Lima)
HISTORICO = ARCHIVO / "focos_historico"       # AAAA/focos_AAAA-MM.csv.gz (carga FIRMS 2020–hoy)
SALIDA = RAIZ / "docs" / "data"
INICIO_SERIE = "2020-01"

# Criterio de fuente persistente (antorchas, industrias, volcanes)
CELDA_GRADOS = 0.004        # ~400 m
DIAS_PERSISTENTE = 4        # días distintos con focos en la misma celda...
VENTANA_PERSISTENTE = 30    # ...dentro de cualquier ventana de 30 días

# Sensores con serie continua desde 2020 (NOAA-21 empieza en 2024 y sesgaría la tendencia)
SENSORES_COMPARABLES = ("VIIRS S-NPP", "VIIRS NOAA-20")

COLUMNAS = ["fecha_pe", "hora_pe", "acq_date", "acq_time", "latitude", "longitude", "sensor", "producto",
            "frp", "confianza", "daynight", "departamento", "zona", "area", "categoria", "persistente", "valido"]
CLAVE = ["sensor", "latitude", "longitude", "acq_date", "acq_time"]


# --------------------------------------------------------------------------- #
# Persistencia
# --------------------------------------------------------------------------- #
def celda(lat: pd.Series, lon: pd.Series) -> pd.Series:
    return (np.floor(lat / CELDA_GRADOS).astype(int).astype(str) + "_" +
            np.floor(lon / CELDA_GRADOS).astype(int).astype(str))


def marcar_persistentes(cd: pd.DataFrame) -> set[tuple[str, str]]:
    """Recibe columnas celda y acq_date (AAAA-MM-DD). Devuelve los pares (celda, día) que
    pertenecen a una racha de >= DIAS_PERSISTENTE días distintos dentro de VENTANA_PERSISTENTE días."""
    if cd.empty:
        return set()
    u = cd[["celda", "acq_date"]].drop_duplicates()
    n = u.groupby("celda").size()
    u = u[u.celda.isin(n[n >= DIAS_PERSISTENTE].index)]
    salida: set[tuple[str, str]] = set()
    k = DIAS_PERSISTENTE - 1
    for c, g in u.groupby("celda"):
        dias = np.sort(pd.to_datetime(g.acq_date).to_numpy().astype("datetime64[D]").astype(int))
        marca = np.zeros(len(dias), bool)
        for j in range(k, len(dias)):
            if dias[j] - dias[j - k] <= VENTANA_PERSISTENTE - 1:
                marca[j - k:j + 1] = True
        for d in dias[marca]:
            salida.add((c, str(np.datetime64(int(d), "D"))))
    return salida


def con_fecha_pe(df: pd.DataFrame) -> pd.DataFrame:
    t = pd.to_datetime(df.acq_date.astype(str) + " " + df.acq_time.astype(int).astype(str).str.zfill(4),
                       format="%Y-%m-%d %H%M", utc=True).dt.tz_convert("America/Lima")
    df["fecha_pe"] = t.dt.strftime("%Y-%m-%d")
    df["hora_pe"] = t.dt.strftime("%H:%M")
    return df


def normalizar(df: pd.DataFrame) -> pd.DataFrame:
    """Deja un DataFrame con el esquema del archivo (columnas faltantes con valor por defecto)."""
    df = df.copy()
    if "fecha_pe" not in df or df.fecha_pe.isna().any():
        df = con_fecha_pe(df)
    defaults = {"producto": "NRT", "persistente": False, "valido": True, "area": "", "categoria": ""}
    for c in COLUMNAS:
        if c not in df:
            df[c] = defaults.get(c, "")
    df["persistente"] = df.persistente.astype(str).str.lower().isin(["true", "1"])
    df["valido"] = df.valido.astype(str).str.lower().isin(["true", "1"])
    df["area"] = df.area.fillna("")
    df["categoria"] = df.categoria.fillna("")
    return df[COLUMNAS]


# --------------------------------------------------------------------------- #
# Archivo diario (día de Lima)
# --------------------------------------------------------------------------- #
def ruta_diaria(dia: str) -> Path:
    return DIARIO / dia[:7] / f"focos_{dia}.csv"


def leer_diarios(desde: str | None = None, hasta: str | None = None) -> pd.DataFrame:
    partes = []
    for f in sorted(DIARIO.glob("*/focos_*.csv")):
        dia = f.stem.split("_")[-1]
        if (desde and dia < desde) or (hasta and dia > hasta):
            continue
        partes.append(pd.read_csv(f, dtype={"area": str, "categoria": str}))
    if not partes:
        return pd.DataFrame(columns=COLUMNAS)
    return normalizar(pd.concat(partes, ignore_index=True))


def migrar_diarios() -> int:
    """Migración única: los archivos del esquema anterior (sin fecha_pe, cortados por día UTC y con
    focos ya filtrados) se reescriben con el esquema actual y se reparten por día de Lima."""
    viejos = [f for f in sorted(DIARIO.glob("*/focos_*.csv")) if "fecha_pe" not in f.open().readline()]
    if not viejos:
        return 0
    df = pd.concat([pd.read_csv(f, dtype={"area": str, "categoria": str}) for f in viejos], ignore_index=True)
    df["valido"], df["persistente"], df["producto"] = True, False, "NRT"
    for f in viejos:
        f.unlink()
    escribir_diarios(df, migrar=False)
    return len(viejos)


def escribir_diarios(df: pd.DataFrame, persistentes: set[tuple[str, str]] | None = None, ventana_dias: int = 40,
                     migrar: bool = True) -> None:
    """Fusiona df en los archivos diarios (la versión nueva de cada foco reemplaza a la anterior)
    y actualiza la bandera de persistencia de los días recientes ya archivados."""
    if migrar:
        migrar_diarios()
    df = normalizar(df)
    tocados = set(df.fecha_pe.unique())
    for dia, parte in df.groupby("fecha_pe"):
        f = ruta_diaria(dia)
        f.parent.mkdir(parents=True, exist_ok=True)
        if f.exists():
            parte = pd.concat([normalizar(pd.read_csv(f, dtype={"area": str, "categoria": str})), parte], ignore_index=True)
        parte = parte.drop_duplicates(subset=CLAVE, keep="last").sort_values(["acq_date", "acq_time"])
        parte.to_csv(f, index=False)
    if not persistentes:
        return
    limite = (date.today() - timedelta(days=ventana_dias)).isoformat()
    for f in sorted(DIARIO.glob("*/focos_*.csv")):
        dia = f.stem.split("_")[-1]
        if dia < limite or dia in tocados:
            continue
        a = normalizar(pd.read_csv(f, dtype={"area": str, "categoria": str}))
        claves = list(zip(celda(a.latitude, a.longitude), a.acq_date))
        nueva = a.persistente | pd.Series([k in persistentes for k in claves], index=a.index)
        if (nueva != a.persistente).any():
            a["persistente"] = nueva
            a["valido"] = a.valido & ~nueva
            a.to_csv(f, index=False)


def contexto_persistencia(dias: int = 40) -> pd.DataFrame:
    """Celdas y días de focos archivados recientes (sin confianza baja) para el filtro móvil."""
    desde = (date.today() - timedelta(days=dias)).isoformat()
    a = leer_diarios(desde=desde)
    if a.empty:
        return pd.DataFrame(columns=["celda", "acq_date"])
    a = a[a.confianza != "baja"]
    return pd.DataFrame({"celda": celda(a.latitude, a.longitude), "acq_date": a.acq_date.astype(str)})


# --------------------------------------------------------------------------- #
# Superficie de las ANP
# --------------------------------------------------------------------------- #
def _area_anillo_km2(xy: np.ndarray) -> float:
    lat0 = np.radians(xy[:, 1].mean())
    x = np.radians(xy[:, 0]) * 6371.0088 * np.cos(lat0)
    y = np.radians(xy[:, 1]) * 6371.0088
    return abs(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def superficies_km2(capas) -> dict[str, float]:
    """Superficie (km²) de cada área de las capas de ANP (nombre oficial -> km²)."""
    out: dict[str, float] = {}
    for _tipo, capa in capas:
        for it in capa.items:
            s = 0.0
            for ruta, huecos, _lo, _hi in it["partes"]:
                s += _area_anillo_km2(ruta.vertices) - sum(_area_anillo_km2(h.vertices) for h in huecos)
            out[it["nombre"]] = out.get(it["nombre"], 0.0) + s
    return {k: round(v, 1) for k, v in out.items()}


# --------------------------------------------------------------------------- #
# Serie mensual 2020–hoy
# --------------------------------------------------------------------------- #
def _meses(desde: str = INICIO_SERIE) -> list[str]:
    hoy = pd.Timestamp.now(tz="America/Lima").strftime("%Y-%m")
    return [p.strftime("%Y-%m") for p in pd.period_range(desde, hoy, freq="M")]


def _firma(paths: list[Path]) -> str:
    return "|".join(f"{p.name}:{p.stat().st_size}" for p in paths if p.exists())


def _agregar(df: pd.DataFrame) -> dict:
    v = df[df.valido]
    comp = v.sensor.isin(SENSORES_COMPARABLES)
    zonas = {"anp": "Dentro de ANP", "za": "Zona de amortiguamiento", "fuera": "Fuera de ANP"}
    tot = {k: int((v.zona == z).sum()) for k, z in zonas.items()}
    tot_c = {k: int(((v.zona == z) & comp).sum()) for k, z in zonas.items()}
    por_area = {}
    sub = v[v.zona != "Fuera de ANP"]
    for (area, zona), g in sub.groupby(["area", "zona"]):
        clave = ("ZA · " if zona == "Zona de amortiguamiento" else "") + str(area)
        por_area[clave] = [int(len(g)), int(g.sensor.isin(SENSORES_COMPARABLES).sum()), round(float(g.frp.sum()), 1)]
    prod = sorted(set(df.producto.astype(str)))
    return {"todos": tot, "comparable": tot_c, "frp_anp": round(float(v[v.zona == "Dentro de ANP"].frp.sum()), 1),
            "areas": por_area, "producto": "+".join(prod) if prod else "",
            "brutos": int(len(df)), "persistentes": int(df.persistente.sum()), "baja": int((df.confianza == "baja").sum())}


def construir_serie(capas, forzar: bool = False) -> dict:
    """Une carga histórica + archivo diario por mes, escribe los CSV mensuales comprimidos que usa el
    constructor de descargas y la serie agregada docs/data/serie_focos.json. Solo recalcula los meses
    cuyos archivos de entrada cambiaron."""
    dest = SALIDA / "historico"
    dest.mkdir(parents=True, exist_ok=True)
    indice_f = dest / "indice.json"
    indice = json.loads(indice_f.read_text()) if indice_f.exists() and not forzar else {}
    actual = _meses()[-1]
    meses_out = {}
    for m in _meses():
        entradas = [HISTORICO / m[:4] / f"focos_{m}.csv.gz", *sorted((DIARIO / m).glob("focos_*.csv"))]
        entradas = [p for p in entradas if p.exists()]
        firma = _firma(entradas)
        salida_m = dest / f"focos_{m}.csv.gz"
        if not entradas:
            continue
        previo = indice.get(m)
        if previo and previo.get("firma") == firma and salida_m.exists() and m != actual:
            meses_out[m] = previo
            continue
        partes = []
        h = HISTORICO / m[:4] / f"focos_{m}.csv.gz"
        if h.exists():
            partes.append(normalizar(pd.read_csv(h, dtype={"area": str, "categoria": str})))
        for f in sorted((DIARIO / m).glob("focos_*.csv")):
            partes.append(normalizar(pd.read_csv(f, dtype={"area": str, "categoria": str})))
        df = pd.concat(partes, ignore_index=True)
        # SP (procesamiento estándar) tiene prioridad sobre NRT cuando el mismo foco está en ambos
        df["_p"] = (df.producto != "SP").astype(int)
        df = df.sort_values("_p").drop_duplicates(subset=CLAVE, keep="first").drop(columns="_p")
        df = df.sort_values(["fecha_pe", "hora_pe"])
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
            gz.write(df.to_csv(index=False).encode())
        salida_m.write_bytes(buf.getvalue())
        meses_out[m] = {"firma": firma, "desde": df.fecha_pe.min(), "hasta": df.fecha_pe.max(), **_agregar(df)}
    indice_f.write_text(json.dumps(meses_out, ensure_ascii=False))

    km2 = superficies_km2(capas)
    cat = {it["nombre"]: (it["extra"].get("cat") or tipo) for tipo, capa in capas for it in capa.items}
    meses = sorted(meses_out)
    areas: dict[str, dict] = {}
    for m in meses:
        for a, vals in meses_out[m]["areas"].items():
            areas.setdefault(a, {})[m] = vals
    serie = {
        "actualizado": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "inicio": INICIO_SERIE,
        "meses": meses,
        "cobertura": {m: {"desde": meses_out[m]["desde"], "hasta": meses_out[m]["hasta"], "producto": meses_out[m]["producto"]} for m in meses},
        "totales": {m: {k: meses_out[m][k] for k in ("todos", "comparable", "frp_anp", "brutos", "persistentes", "baja")} for m in meses},
        "areas": {a: {"cat": "Zona de amortiguamiento" if a.startswith("ZA · ") else cat.get(a, ""),
                      "km2": None if a.startswith("ZA · ") else km2.get(a), "m": v} for a, v in areas.items()},
        "criterios": {"celda_grados": CELDA_GRADOS, "dias_persistente": DIAS_PERSISTENTE,
                      "ventana_persistente_dias": VENTANA_PERSISTENTE, "sensores_comparables": list(SENSORES_COMPARABLES),
                      "valores_por_area": ["focos (todos los sensores)", "focos (sensores comparables)", "FRP total (MW)"]},
    }
    (SALIDA / "serie_focos.json").write_text(json.dumps(serie, ensure_ascii=False, separators=(",", ":")))
    return {"meses": len(meses), "desde": meses[0] if meses else None, "hasta": meses[-1] if meses else None,
            "ultimo_dato": max((v["hasta"] for v in meses_out.values()), default=None)}
