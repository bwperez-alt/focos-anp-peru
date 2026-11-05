"""Pérdida histórica de cobertura arbórea por ANP y zona de amortiguamiento (2001 – último año disponible).

Fuente: Hansen, M. C. et al. (2013). High-Resolution Global Maps of 21st-Century Forest Cover Change.
Science 342: 850–853. Global Forest Change (Univ. de Maryland / Google), capa "lossyear", 30 m.
https://glad.earthengine.app/view/global-forest-change  (licencia CC BY 4.0)

Se ejecuta en GitHub Actions (workflow "Pérdida histórica de bosque"): descarga las teselas que cubren
el Perú, cuenta los píxeles de pérdida por año dentro de cada ANP y de su zona de amortiguamiento
(excluyendo el ANP) y convierte a hectáreas con el área real de cada píxel según la latitud.
Solo recalcula si GFC publicó una versión nueva.
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline import BASE, RAIZ, SALIDA, nombre_oficial  # noqa: E402

BUCKET = "https://storage.googleapis.com/earthenginepartners-hansen"
VERSIONES = [f"GFC-{a}-v1.{a - 2012}" for a in range(datetime.now().year, 2022, -1)]  # p. ej. GFC-2025-v1.13
SALIDA_JSON = SALIDA / "perdida_historica.json"


def version_disponible() -> str:
    for v in VERSIONES:
        u = f"{BUCKET}/{v}/Hansen_{v}_lossyear_10S_080W.tif"
        if requests.head(u, timeout=60).status_code == 200:
            return v
    raise RuntimeError("No se encontró ninguna versión de Global Forest Change")


def teselas(bounds) -> list[str]:
    x0, y0, x1, y1 = bounds
    out = []
    for top in range(int(math.ceil(y1 / 10) * 10), int(math.floor(y0 / 10) * 10), -10):
        for left in range(int(math.floor(x0 / 10) * 10), int(math.ceil(x1 / 10) * 10), 10):
            ns = f"{abs(top):02d}{'N' if top >= 0 else 'S'}"
            ew = f"{abs(left):03d}{'E' if left >= 0 else 'W'}"
            out.append((f"{ns}_{ew}", (left, top - 10, left + 10, top)))
    return out


def cargar_geometrias():
    anp = []
    for archivo, nom, cat in [("anp_nacional.geojson", lambda p: nombre_oficial(p.get("anp_cate"), p.get("anp_nomb")), lambda p: p.get("anp_cate", "")),
                              ("zonas_reservadas.geojson", lambda p: nombre_oficial("Zona Reservada", p.get("zr_nomb")), lambda p: "Zona Reservada"),
                              ("acr.geojson", lambda p: nombre_oficial("Área de Conservación Regional", p.get("acr_nomb")), lambda p: "Área de Conservación Regional"),
                              ("acp.geojson", lambda p: nombre_oficial("Área de Conservación Privada", p.get("acp_nomb")), lambda p: "Área de Conservación Privada")]:
        for f in json.loads((BASE / archivo).read_text())["features"]:
            if f.get("geometry"):
                p = f["properties"]
                codi = p.get("anp_codi") or p.get("zr_codi") or p.get("acr_codi") or p.get("acp_codi")
                anp.append({"area": nom(p), "categoria": cat(p), "zona": "Dentro de ANP", "codi": codi, "geom": f["geometry"]})
    completo = {a["codi"]: a["area"] for a in anp}
    za = []
    for f in json.loads((BASE / "zonas_amortiguamiento.geojson").read_text())["features"]:
        if f.get("geometry"):
            p = f["properties"]
            za.append({"area": completo.get(p.get("anp_codi"), p.get("anp_nomb")), "categoria": "Zona de amortiguamiento",
                       "zona": "Zona de amortiguamiento", "codi": p.get("anp_codi"), "geom": f["geometry"]})
    return anp, za


def bbox(geom):
    coords = []
    def walk(c):
        if isinstance(c[0], (int, float)):
            coords.append(c)
        else:
            for x in c:
                walk(x)
    walk(geom["coordinates"])
    a = np.asarray(coords)
    return a[:, 0].min(), a[:, 1].min(), a[:, 0].max(), a[:, 1].max()


def interseca(b, t):
    return not (b[2] <= t[0] or b[0] >= t[2] or b[3] <= t[1] or b[1] >= t[3])


def main(forzar: bool = False):
    version = version_disponible()
    previo = json.loads(SALIDA_JSON.read_text()) if SALIDA_JSON.exists() else {}
    if previo.get("version") == version and not forzar:
        print("Sin versión nueva de GFC:", version)
        return
    anio_fin = int(version.split("-")[1])
    anios = list(range(2001, anio_fin + 1))
    anp, za = cargar_geometrias()
    for x in anp + za:
        x["bbox"] = bbox(x["geom"])
        x["ha"] = np.zeros(len(anios) + 1)
    todo = (min(x["bbox"][0] for x in anp + za), min(x["bbox"][1] for x in anp + za), max(x["bbox"][2] for x in anp + za), max(x["bbox"][3] for x in anp + za))
    tmp = Path(tempfile.mkdtemp())
    for nombre, tb in teselas(todo):
        objetivos = [x for x in anp + za if interseca(x["bbox"], tb)]
        if not objetivos:
            continue
        url = f"{BUCKET}/{version}/Hansen_{version}_lossyear_{nombre}.tif"
        print("Tesela", nombre, len(objetivos), "áreas")
        ruta = tmp / f"{nombre}.tif"
        with requests.get(url, stream=True, timeout=600) as r:
            if r.status_code != 200:
                print("  no disponible", r.status_code)
                continue
            with open(ruta, "wb") as fh:
                for chunk in r.iter_content(1 << 22):
                    fh.write(chunk)
        with rasterio.open(ruta) as src:
            res = src.res[0]
            for x in objetivos:
                b = x["bbox"]
                w = from_bounds(max(b[0], tb[0]), max(b[1], tb[1]), min(b[2], tb[2]), min(b[3], tb[3]), src.transform).round_offsets().round_lengths()
                if w.width <= 0 or w.height <= 0:
                    continue
                datos = src.read(1, window=w)
                tr = src.window_transform(w)
                dentro = geometry_mask([x["geom"]], out_shape=datos.shape, transform=tr, invert=True)
                if x["zona"] == "Zona de amortiguamiento":  # excluir el propio ANP (y otras ANP) de la franja
                    otras = [a["geom"] for a in anp if interseca(a["bbox"], x["bbox"])]
                    if otras:
                        dentro &= geometry_mask(otras, out_shape=datos.shape, transform=tr, invert=False)
                if not dentro.any():
                    continue
                lat = tr.f + (np.arange(datos.shape[0]) + 0.5) * tr.e
                area_ha = (res * 111320 * np.cos(np.radians(lat))) * (res * 110574) / 1e4
                pesos = np.broadcast_to(area_ha[:, None], datos.shape)[dentro]
                x["ha"] += np.bincount(datos[dentro], weights=pesos, minlength=len(anios) + 1)[: len(anios) + 1]
        ruta.unlink()

    filas = []
    for x in anp + za:
        serie = x["ha"][1:]
        if serie.sum() <= 0:
            continue
        filas.append({"area": x["area"], "categoria": x["categoria"], "zona": x["zona"],
                      "total_ha": round(float(serie.sum()), 1), "ultimos5_ha": round(float(serie[-5:].sum()), 1),
                      "ultimo_anio_ha": round(float(serie[-1]), 1), "por_anio": [round(float(v), 1) for v in serie]})
    # agrupa polígonos múltiples de una misma área
    df = pd.DataFrame(filas)
    agg = []
    for (a, z), g in df.groupby(["area", "zona"]):
        serie = np.sum(np.vstack(g.por_anio.to_list()), axis=0)
        agg.append({"area": a, "zona": z, "categoria": g.categoria.iat[0], "total_ha": round(float(serie.sum()), 1),
                    "ultimos5_ha": round(float(serie[-5:].sum()), 1), "ultimo_anio_ha": round(float(serie[-1]), 1),
                    "por_anio": [round(float(v), 1) for v in serie]})
    agg.sort(key=lambda r: -r["total_ha"])
    tot = lambda z: [round(sum(r["por_anio"][i] for r in agg if r["zona"] == z), 1) for i in range(len(anios))]
    res = {"fuente": "Hansen et al. (2013), Global Forest Change – Univ. de Maryland / Google (lossyear, 30 m)",
           "url": "https://glad.earthengine.app/view/global-forest-change", "licencia": "CC BY 4.0",
           "version": version, "anios": anios, "generado": datetime.now(timezone.utc).isoformat(timespec="minutes"),
           "nota": "Pérdida de cobertura arbórea (no solo deforestación: incluye incendios, tala selectiva y causas naturales). Geometrías simplificadas (~300 m).",
           "totales": {"anp": tot("Dentro de ANP"), "za": tot("Zona de amortiguamiento")},
           "areas": agg}
    SALIDA.mkdir(parents=True, exist_ok=True)
    SALIDA_JSON.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    arch = RAIZ / "data" / "archivo"
    arch.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"area": r["area"], "zona": r["zona"], "categoria": r["categoria"], "anio": y, "perdida_ha": v}
                  for r in agg for y, v in zip(anios, r["por_anio"])]).to_csv(arch / f"perdida_bosque_{version}.csv", index=False)
    print("Listo:", len(agg), "áreas;", "ANP total ha:", round(sum(res["totales"]["anp"]), 1))


if __name__ == "__main__":
    main(forzar=os.environ.get("FORZAR") == "1")
