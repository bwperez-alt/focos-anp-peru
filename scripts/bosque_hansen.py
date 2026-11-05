"""Pérdida de cobertura arbórea 2001–2025 por ANP y zona de amortiguamiento.

Fuente: Hansen, M. C. et al. (2013). High-Resolution Global Maps of 21st-Century Forest Cover Change.
Science 342: 850–853. Global Forest Change 2000–2025 (v1.13), Universidad de Maryland / Google.
https://glad.earthengine.app/view/global-forest-change  (licencia CC BY 4.0)

Se procesa una vez al año (workflow 'bosques-anual'): descarga las teselas 'lossyear' que cubren
el Perú y suma, para cada polígono, el área de los píxeles de 30 m cuya pérdida ocurrió en cada año.

    pip install rasterio numpy && python scripts/bosque_hansen.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline import BASE, RAIZ, nombre_oficial  # noqa: E402

VERSION = "GFC-2025-v1.13"
ANIO_FIN = 2025
TESELAS = ["00N_090W", "00N_080W", "00N_070W", "10S_080W", "10S_070W"]
URL = "https://storage.googleapis.com/earthenginepartners-hansen/{v}/Hansen_{v}_lossyear_{t}.tif"
DIR_TESELAS = RAIZ / "data" / "tmp_hansen"
SALIDA = RAIZ / "docs" / "estatico"
ARCHIVO = RAIZ / "data" / "archivo"


def poligonos() -> list[dict]:
    """ANP (nacional, ZR, ACR, ACP) y zonas de amortiguamiento como geometrías GeoJSON."""
    out = []
    capas = [("anp_nacional.geojson", "Dentro de ANP", lambda p: nombre_oficial(p.get("anp_cate"), p.get("anp_nomb")), "anp_codi"),
             ("zonas_reservadas.geojson", "Dentro de ANP", lambda p: nombre_oficial("Zona Reservada", p.get("zr_nomb")), "zr_codi"),
             ("acr.geojson", "Dentro de ANP", lambda p: nombre_oficial("Área de Conservación Regional", p.get("acr_nomb")), "acr_codi"),
             ("acp.geojson", "Dentro de ANP", lambda p: nombre_oficial("Área de Conservación Privada", p.get("acp_nomb")), "acp_codi")]
    nombres_codi = {}
    for archivo, zona, nombre, campo in capas:
        for f in json.loads((BASE / archivo).read_text())["features"]:
            if f.get("geometry"):
                n = nombre(f["properties"])
                nombres_codi[f["properties"].get(campo)] = n
                out.append({"area": n, "zona": zona, "codi": f["properties"].get(campo), "geom": f["geometry"]})
    for f in json.loads((BASE / "zonas_amortiguamiento.geojson").read_text())["features"]:
        if f.get("geometry"):
            c = f["properties"].get("anp_codi")
            out.append({"area": nombres_codi.get(c, f["properties"].get("anp_nomb")), "zona": "Zona de amortiguamiento", "codi": c, "geom": f["geometry"]})
    return out


def bbox(geom) -> tuple[float, float, float, float]:
    xs, ys = [], []
    def rec(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for x in c:
                rec(x)
    rec(geom["coordinates"])
    return min(xs), min(ys), max(xs), max(ys)


def main() -> None:
    import urllib.request
    DIR_TESELAS.mkdir(parents=True, exist_ok=True)
    polis = poligonos()
    anp_por_codi = {}
    for p in polis:
        if p["zona"] == "Dentro de ANP":
            anp_por_codi.setdefault(p["codi"], []).append(p["geom"])
    n_anios = ANIO_FIN - 2000
    acum: dict[tuple[str, str], np.ndarray] = {}
    for t in TESELAS:
        ruta = DIR_TESELAS / f"{t}.tif"
        if not ruta.exists():
            print("Descargando", t, flush=True)
            urllib.request.urlretrieve(URL.format(v=VERSION, t=t), ruta)
        with rasterio.open(ruta) as src:
            tb = src.bounds
            for p in polis:
                x0, y0, x1, y1 = bbox(p["geom"])
                ix0, iy0, ix1, iy1 = max(x0, tb.left), max(y0, tb.bottom), min(x1, tb.right), min(y1, tb.top)
                if ix0 >= ix1 or iy0 >= iy1:
                    continue
                win = from_bounds(ix0, iy0, ix1, iy1, src.transform).round_offsets().round_lengths()
                if win.width < 1 or win.height < 1:
                    continue
                arr = src.read(1, window=win)
                tr = src.window_transform(win)
                dentro = geometry_mask([p["geom"]], out_shape=arr.shape, transform=tr, invert=True)
                if p["zona"] == "Zona de amortiguamiento" and p["codi"] in anp_por_codi:
                    dentro &= ~geometry_mask(anp_por_codi[p["codi"]], out_shape=arr.shape, transform=tr, invert=True)
                filas, = np.nonzero(dentro.any(axis=1))
                if not len(filas):
                    continue
                # área del píxel (ha) según la latitud de cada fila
                lat = tr.f + (np.arange(arr.shape[0]) + 0.5) * tr.e
                area_px = (abs(tr.a) * 111_320) * (abs(tr.e) * 110_574) * np.cos(np.radians(lat)) / 10_000
                v = np.where(dentro, arr, 0).astype(np.int64)
                v = np.clip(v, 0, n_anios)
                idx = (np.arange(arr.shape[0])[:, None] * (n_anios + 1) + v).ravel()
                conteo = np.bincount(idx, minlength=arr.shape[0] * (n_anios + 1)).reshape(arr.shape[0], n_anios + 1)
                ha = (conteo * area_px[:, None]).sum(axis=0)[1:]
                clave = (p["area"], p["zona"])
                acum[clave] = acum.get(clave, np.zeros(n_anios)) + ha
        print("  tesela", t, "procesada", flush=True)

    anios = list(range(2001, ANIO_FIN + 1))
    filas = [{"area": a, "zona": z, **{str(y): round(float(v[i]), 1) for i, y in enumerate(anios)}, "total": round(float(v.sum()), 1)}
             for (a, z), v in acum.items()]
    filas.sort(key=lambda r: -r["total"])
    nac = {z: [round(float(sum(acum[k][i] for k in acum if k[1] == z)), 1) for i in range(n_anios)] for z in ("Dentro de ANP", "Zona de amortiguamiento")}
    res = {"fuente": "Hansen et al. (2013), Global Forest Change 2000–2025 (v1.13), Universidad de Maryland",
           "url": "https://glad.earthengine.app/view/global-forest-change", "licencia": "CC BY 4.0",
           "nota": "Pérdida de cobertura arbórea (no solo deforestación: incluye incendios, tala y causas naturales) en píxeles de 30 m. "
                   "Las zonas de amortiguamiento excluyen la superficie del ANP. Polígonos simplificados (~300 m).",
           "generado": datetime.now(timezone.utc).isoformat(timespec="minutes"), "anios": anios,
           "serie_nacional": nac, "areas": filas}
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "hansen.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    import csv
    ARCHIVO.mkdir(parents=True, exist_ok=True)
    with open(ARCHIVO / "hansen_perdida_anp_ha.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["area", "zona", *map(str, anios), "total"])
        w.writeheader(); w.writerows(filas)
    print("Listo:", len(filas), "áreas; total en ANP:", round(sum(nac["Dentro de ANP"])), "ha")


if __name__ == "__main__":
    main()
