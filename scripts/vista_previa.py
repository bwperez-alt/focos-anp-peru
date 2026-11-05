"""Genera una versión autocontenida del dashboard (datos incrustados) para compartir sin servidor."""
import json, re, sys
from pathlib import Path
R = Path(__file__).resolve().parents[1]
D = R / "docs" / "data"
html = (R / "docs" / "index.html").read_text()
L = lambda p: json.loads(p.read_text())
datos = {"res": L(D / "resumen.json"), "focos": L(D / "focos.geojson"),
         "capas": {k: L(D / "capas" / f"{f}.geojson") for k, f in
                   [("anp", "anp_nacional"), ("zr", "zonas_reservadas"), ("acr", "acr"), ("acp", "acp"), ("za", "zonas_amortiguamiento")]}}
dep = L(R / "data" / "base" / "departamentos.geojson")
estilo = {"version": 8, "sources": {"dep": {"type": "geojson", "data": dep}},
          "layers": [{"id": "bg", "type": "background", "paint": {"background-color": "#121513"}},
                     {"id": "dep-f", "type": "fill", "source": "dep", "paint": {"fill-color": "#1b1f1c"}},
                     {"id": "dep-l", "type": "line", "source": "dep", "paint": {"line-color": "#3a403c", "line-width": 0.8}}]}
iny = "<script>window.__DATOS__=" + json.dumps(datos, ensure_ascii=False, separators=(",", ":")) + ";window.__ESTILO__=" + json.dumps(estilo, separators=(",", ":")) + ";</script>\n"
css = "<style>.maplibregl-map{position:relative;overflow:hidden;-webkit-tap-highlight-color:transparent}.maplibregl-canvas{position:absolute;left:0;top:0}.maplibregl-ctrl-top-right{position:absolute;top:0;right:0;z-index:2}.maplibregl-ctrl{margin:10px}.maplibregl-ctrl-group{background:#1e2220;border-radius:6px}.maplibregl-ctrl-group button{display:block;width:30px;height:30px;border:0;background:transparent;color:#eeede8;font-size:18px;cursor:pointer}.maplibregl-ctrl-zoom-in:after{content:'+'}.maplibregl-ctrl-zoom-out:after{content:'\\2212'}.maplibregl-ctrl-bottom-right{position:absolute;right:0;bottom:0}.maplibregl-ctrl-attrib-button{display:none}</style>\n"
html = html.replace("</style>", "</style>\n" + css, 1)
html = html.replace("<script>\nconst ZONAS", iny + "<script>\nconst ZONAS", 1)
if "--fragmento" in sys.argv:  # sin <html>/<head>/<body> propios
    html = re.sub(r'<link href="https://unpkg.com[^>]*>\n', "", html)
    html = re.sub(r"<!doctype html>\s*<html[^>]*>\s*<head>\s*", "", html, flags=re.I)
    html = re.sub(r"</head>\s*<body>\s*", "", html, flags=re.I)
    html = re.sub(r"</body>\s*</html>\s*$", "", html, flags=re.I)
out = Path(sys.argv[1])
out.write_text(html)
print(out, f"{len(html)/1e6:.2f} MB")
