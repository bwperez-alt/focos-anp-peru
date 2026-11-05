"""Descarga de nuevo las capas oficiales del SERNANP a data/base/ (ejecutar a mano cuando cambien).

python scripts/actualizar_capas_base.py
"""
import json
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parents[1] / "data" / "base"
SRV = "https://geoservicios.sernanp.gob.pe/arcgis/rest/services/servicios_ogc"
CAPAS = {
    "anp_nacional": ("peru_sernanp_0102", 0, "anp_codi,anp_cate,anp_nomb,anp_ubpo"),
    "zonas_reservadas": ("peru_sernanp_0102", 1, "zr_codi,zr_nomb,zr_ubpo"),
    "acr": ("peru_sernanp_0102", 2, "acr_codi,acr_nomb,acr_ubpo"),
    "acp": ("peru_sernanp_0102", 3, "acp_codi,acp_nomb,acp_ubpo"),
    "zonas_amortiguamiento": ("peru_sernanp_0214", 0, "anp_codi,anp_nomb"),
}

for nombre, (srv, capa, campos) in CAPAS.items():
    url = f"{SRV}/{srv}/MapServer/{capa}/query"
    params = {"where": "1=1", "outFields": campos, "outSR": 4326, "maxAllowableOffset": 0.003,
              "geometryPrecision": 4, "f": "geojson"}
    gj = requests.get(url, params=params, timeout=120).json()
    (BASE / f"{nombre}.geojson").write_text(json.dumps(gj, ensure_ascii=False, separators=(",", ":")))
    print(f"{nombre}: {len(gj['features'])} polígonos")
