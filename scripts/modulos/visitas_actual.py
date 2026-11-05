"""Flujo turístico actual – MINCETUR, Datos Turismo (fuentes: SERNANP, Ministerio de Cultura, encuesta de hospedajes).

1) Llegada mensual de visitantes (nacionales y extranjeros) a ANP con registro propio:
   Huascarán, Machu Picchu, Tingo María, Paracas, Islas Ballestas, Bosque de Pómac, Pacaya Samiria, Tambopata, Titicaca.
2) Arribos de huéspedes a establecimientos de hospedaje por región (acumulado del año frente al año anterior):
   indicador actual del flujo turístico para las ANP sin conteo propio publicado.

https://datosturismo.mincetur.gob.pe/appdatosturismo/content2.html
Se descarga una vez al día como máximo (el MINCETUR actualiza mensualmente).
"""
from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from .sernanp_datos import clave, emparejar

BASE = "https://datosturismo.mincetur.gob.pe"
WEB = BASE + "/appdatosturismo/content2.html"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
CORTO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
ANIO_INICIO = 2019
NO_ANP = re.compile(r"colca|wariwilca|circuito|museo", re.I)
ES_ANP = re.compile(r"parque nacional|reserva nacional|santuario hist|santuario nacional|islas ballestas|bosque de protecci|refugio de vida|reserva paisaj", re.I)
REPORTE_REGIONES = "310"   # Arribo a establecimientos de hospedaje, según región


def exportar(s: requests.Session, rid: str, ini: int, fin: int) -> bytes:
    u = f"{BASE}/appdatosturismo/frmReporte.aspx?id={rid}"
    t = s.get(u, timeout=60).text
    data = dict(re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', t))
    for n in re.findall(r'<select[^>]*name="([^"]+)"', t):
        data[n] = ("12" if "FIN" in n else "1") if "MES" in n else str(fin if "FIN" in n else ini)
    for b, v in re.findall(r'<input[^>]*type="submit"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', t):
        data[b] = v
    t2 = s.post(u, data=data, timeout=120).text
    m = re.search(r'(/appDatosTurismo/Reserved\.ReportViewerWebControl\.axd\?Culture=[^"\']*?OpType=Export[^"\']*?Format=)', t2)
    if not m:
        raise RuntimeError(f"Reporte {rid}: sin enlace de exportación")
    x = s.get(BASE + m.group(1).replace("\\u0026", "&") + "EXCEL", timeout=120)
    x.raise_for_status()
    return x.content


def nota_corte(xl: pd.DataFrame) -> str | None:
    for v in xl.astype(str).values.ravel():
        m = re.search(r"disponible al (\d{1,2} de \w+ (?:de|del) \d{4})", v, re.I)
        if m:
            return m.group(1)
    return None


def leer_sitio(xl: pd.DataFrame) -> pd.DataFrame:
    """Tabla 'año x (Nacional, Extranjero, Total)' con filas Enero..Diciembre -> formato largo."""
    fila_anios = next(i for i, r in xl.iterrows() if sum(isinstance(v, (int, float)) and 2000 <= v <= 2100 for v in r.tolist()) >= 1)
    anios = {}
    for j, v in enumerate(xl.iloc[fila_anios].tolist()):
        if isinstance(v, (int, float)) and 2000 <= v <= 2100:
            anios[j] = int(v)
    cab = xl.iloc[fila_anios + 1].astype(str).str.lower().tolist()
    cols = []  # (anio, tipo, j)
    anio_actual = None
    for j, c in enumerate(cab):
        if j in anios:
            anio_actual = anios[j]
        if anio_actual and c.strip() in ("nacional", "extranjero", "total"):
            cols.append((anio_actual, c.strip(), j))
    filas = []
    for _, r in xl.iterrows():
        etiqueta = str(r.iloc[0]).strip().lower() if str(r.iloc[0]) != "nan" else next((str(v).strip().lower() for v in r.tolist() if str(v) != "nan"), "")
        if etiqueta not in MESES:
            continue
        valores = r.tolist()
        # las celdas vacías se desplazan en algunas exportaciones: se usan las posiciones de la cabecera
        mes = MESES.index(etiqueta) + 1
        reg = {}
        for anio, tipo, j in cols:
            v = valores[j] if j < len(valores) else None
            if isinstance(v, (int, float)) and not pd.isna(v):
                reg.setdefault(anio, {})[tipo] = float(v)
        for anio, d in reg.items():
            if "total" in d or ("nacional" in d and "extranjero" in d):
                filas.append({"anio": anio, "mes": mes, "nacional": d.get("nacional"), "extranjero": d.get("extranjero"),
                              "total": d.get("total", (d.get("nacional") or 0) + (d.get("extranjero") or 0))})
    return pd.DataFrame(filas)


def leer_regiones(xl: pd.DataFrame) -> tuple[list[dict], str]:
    fila_cab = next(i for i, r in xl.iterrows() if any("Acumulado" in str(v) for v in r.tolist()))
    cab = [str(v) for v in xl.iloc[fila_cab].tolist()]
    idx_acum = [j for j, c in enumerate(cab) if "Acumulado" in c]
    idx_var = next((j for j, c in enumerate(cab) if "Variaci" in c), None)
    periodo = cab[idx_acum[-1]].replace("Acumulado", "").strip() if idx_acum else ""
    filas = []
    for _, r in xl.iloc[fila_cab + 1:].iterrows():
        v = r.tolist()
        nombre = next((str(x).strip() for x in v if isinstance(x, str) and x.strip()), None)
        nums = [x for x in v if isinstance(x, (int, float)) and not pd.isna(x)]
        if not nombre or len(nums) < 3 or nombre.lower().startswith(("nota", "fuente", "elabora")):
            continue
        prev, act = (float(v[idx_acum[0]]), float(v[idx_acum[-1]])) if len(idx_acum) >= 2 else (nums[-3], nums[-2])
        var = float(v[idx_var]) if idx_var is not None and isinstance(v[idx_var], (int, float)) else (100 * (act - prev) / prev if prev else None)
        filas.append({"region": nombre.title().replace(" De ", " de "), "acumulado_previo": round(prev), "acumulado_actual": round(act),
                      "variacion_pct": None if var is None else round(var, 1)})
    return filas, periodo


def ejecutar(salida: Path, archivo: Path, capas_anp) -> dict:
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    previo = salida / "visitas_actual.json"
    if previo.exists():
        try:
            p = json.loads(previo.read_text())
            if p.get("descargado", "")[:10] == hoy:
                return {"omitido": True, "ultimo_dato": p.get("ultimo_mes")}
        except Exception:  # noqa: BLE001
            pass
    s = requests.Session(); s.headers.update(H)
    js = s.get(BASE + "/appdatosturismo/js/reportes.js", timeout=60).text
    i = js.find("var capitulo2"); j = js.find("];", i)
    reportes = [m.groups() for m in re.finditer(r'codigo\s*:\s*"(\d+)"\s*,\s*titulo\s*:\s*[\'"]([^\'"]+)[\'"]\s*,\s*departamento\s*:\s*"([^"]*)"', js[i:j])]
    reportes = [r for r in reportes if ES_ANP.search(r[1]) and not NO_ANP.search(r[1])]

    nombres = [it["nombre"] for _, c in capas_anp for it in c.items]
    buscar = emparejar(nombres)
    def oficial(titulo: str) -> str | None:
        t = re.sub(r"^(la|las|el|los)\s+", "", titulo, flags=re.I)
        t = re.sub(r"\s*\(.*?\)", "", t).replace("Machu Picchu", "Machupicchu").replace("Pacaya Samiria", "Pacaya-Samiria")
        if "ballestas" in t.lower():
            return next((n for n in nombres if "ballestas" in n.lower()), None) or next((n for n in nombres if "islas, islotes" in n.lower()), None)
        m = re.match(r"(parque nacional|reserva nacional|santuario hist[oó]rico|santuario nacional)\s+(.*)", t, re.I)
        n = buscar(m.group(1), m.group(2)) if m else None
        if n:
            return n
        k = clave(t)
        return next((x for x in nombres if clave(x) == k or k in clave(x)), None)

    anio_fin = datetime.now(timezone.utc).year
    sitios, largo, corte, errores = {}, [], None, {}
    for rid, titulo, depto in reportes:
        try:
            xl = pd.read_excel(io.BytesIO(exportar(s, rid, ANIO_INICIO, anio_fin)), header=None, engine="xlrd")
            df = leer_sitio(xl)
            corte = corte or nota_corte(xl)
        except Exception as e:  # noqa: BLE001
            errores[titulo] = f"{type(e).__name__}: {e}"[:150]
            continue
        if df.empty:
            continue
        df = df.sort_values(["anio", "mes"])
        df = df[(df.total > 0) | (df.anio == 2020) | (df.anio == 2021)]
        area = oficial(titulo) or titulo
        df["periodo"] = df.anio.astype(str) + "-" + df.mes.astype(str).str.zfill(2)
        ult = df.iloc[-1]
        prev = df[(df.anio == ult.anio - 1) & (df.mes == ult.mes)]
        acum = df[(df.anio == ult.anio) & (df.mes <= ult.mes)].total.sum()
        acum_prev = df[(df.anio == ult.anio - 1) & (df.mes <= ult.mes)].total.sum()
        perfil_base = df[df.anio >= 2022]
        perfil = perfil_base.groupby("mes").total.mean().reindex(range(1, 13))
        top3 = [int(m) for m in perfil.sort_values(ascending=False).dropna().index[:3]]
        sitios[area] = {
            "reporte": rid, "titulo_mincetur": titulo, "departamento": depto.title(),
            "serie": [{"periodo": r.periodo, "nacional": None if pd.isna(r.nacional) else int(r.nacional),
                       "extranjero": None if pd.isna(r.extranjero) else int(r.extranjero), "total": int(r.total)} for r in df.itertuples()],
            "ultimo": {"periodo": ult.periodo, "total": int(ult.total),
                       "variacion_anual_pct": round(100 * (ult.total - prev.total.iat[0]) / prev.total.iat[0], 1) if len(prev) and prev.total.iat[0] else None},
            "acumulado": {"anio": int(ult.anio), "hasta_mes": CORTO[int(ult.mes) - 1], "actual": int(acum), "previo": int(acum_prev),
                          "variacion_pct": round(100 * (acum - acum_prev) / acum_prev, 1) if acum_prev else None},
            "perfil_mensual": [None if pd.isna(x) else round(float(x)) for x in perfil],
            "meses_pico": [CORTO[m - 1] for m in top3], "meses_pico_num": top3,
            "pct_extranjeros_12m": round(100 * df.tail(12).extranjero.sum() / max(1, df.tail(12).total.sum()), 1) if df.tail(12).extranjero.notna().all() else None,
        }
        largo.append(df.assign(area=area, reporte_mincetur=titulo))

    regiones, periodo_reg = [], ""
    try:
        xl = pd.read_excel(io.BytesIO(exportar(s, REPORTE_REGIONES, anio_fin - 2, anio_fin)), header=None, engine="xlrd")
        regiones, periodo_reg = leer_regiones(xl)
    except Exception as e:  # noqa: BLE001
        errores["regiones"] = f"{type(e).__name__}: {e}"[:150]

    if not sitios and not regiones:
        raise RuntimeError(f"MINCETUR sin datos: {errores}")
    ultimo_mes = max((v["ultimo"]["periodo"] for v in sitios.values()), default=None)
    res = {
        "fuente": "MINCETUR – Datos Turismo (llegada de visitantes a ANP: SERNANP; arribos a hospedajes: encuesta mensual)",
        "url": WEB, "descargado": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "informacion_al": corte, "ultimo_mes": ultimo_mes,
        "nota": "Cifras mensuales oficiales; el MINCETUR las publica con uno o dos meses de desfase. 2020–2021 incluyen cierres por la pandemia.",
        "sitios": sitios,
        "ranking": sorted(({"area": a, "acumulado": v["acumulado"]["actual"], "variacion_pct": v["acumulado"]["variacion_pct"],
                            "hasta": f'{v["acumulado"]["hasta_mes"]} {v["acumulado"]["anio"]}', "ultimo": v["ultimo"]} for a, v in sitios.items()),
                          key=lambda r: -r["acumulado"]),
        "regiones": {"periodo": periodo_reg, "nota": "Arribos de huéspedes a establecimientos de hospedaje (información preliminar).", "filas": regiones},
        "errores": errores or None,
    }
    (salida / "visitas_actual.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    archivo.mkdir(parents=True, exist_ok=True)
    if largo:
        pd.concat(largo)[["area", "reporte_mincetur", "periodo", "anio", "mes", "nacional", "extranjero", "total"]].to_csv(archivo / "visitas_anp_mincetur.csv", index=False)
    if regiones:
        pd.DataFrame(regiones).assign(periodo=periodo_reg).to_csv(archivo / "arribos_hospedaje_region.csv", index=False)
    return {"ultimo_dato": ultimo_mes, "registros": sum(len(v["serie"]) for v in sitios.values()), "sitios": len(sitios), "errores": errores or None}
