"""Sondeo de fuentes oficiales (se ejecuta en GitHub Actions). Imprime un resumen de cada endpoint."""
import json, re, requests
H = {"User-Agent": "Mozilla/5.0 (observatorio-ambiental-peru; investigacion academica)"}
def get(u, **kw):
    try:
        r = requests.get(u, headers=H, timeout=60, **kw)
        return r.status_code, r.headers.get("content-type", ""), r.text
    except Exception as e:
        return "ERR", "", str(e)
def show(nombre, u, n=700, **kw):
    s, ct, t = get(u, **kw)
    print(f"\n===== {nombre}\nURL {u}\nSTATUS {s} | {ct} | {len(t)} chars\n{t[:n]}")
    return t
# Sismos IGP
for y in ["2026"]:
    show("IGP ajaxb", f"https://ultimosismos.igp.gob.pe/api/ultimo-sismo/ajaxb/{y}", 900)
show("IGP home", "https://ultimosismos.igp.gob.pe/", 300)
show("USGS Peru", "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&minlatitude=-18.6&maxlatitude=0.2&minlongitude=-81.6&maxlongitude=-68.5&minmagnitude=3.5&orderby=time&limit=3", 900)
# SENAMHI avisos
t = show("SENAMHI avisos", "https://www.senamhi.gob.pe/?p=aviso-meteorologico", 200)
for m in sorted(set(re.findall(r'["\']([^"\']*(?:aviso|ajax|json|php)[^"\']*)["\']', t)))[:60]:
    print("  ref:", m)
t = show("SENAMHI calidad aire", "https://www.senamhi.gob.pe/mapas/mapa-ca-monitoreo/map_data_ca.php", 150)
# Datos abiertos (DKAN/CKAN API)
for q in ["visitantes areas naturales protegidas", "SERNANP visitantes", "emergencias INDECI", "incendios forestales", "avisos meteorologicos SENAMHI"]:
    t = show("datosabiertos " + q, "https://www.datosabiertos.gob.pe/api/3/action/package_search?q=" + requests.utils.quote(q) + "&rows=8", 200)
    try:
        d = json.loads(t)
        res = d.get("result", {})
        res = res.get("results", res if isinstance(res, list) else [])
        for p in res[:8]:
            print("  *", p.get("title"), "|", p.get("name"), "|", p.get("metadata_modified"), "|", [(x.get("format"), x.get("url")) for x in p.get("resources", [])][:4])
    except Exception as e:
        print("  (no JSON)", e)
# SINPAD / INDECI
show("SINPAD", "https://sinpad.indeci.gob.pe/", 300)
show("INDECI emergencias portal", "https://portal.indeci.gob.pe/emergencias/", 300)
# Geobosques ATD
s, ct, t = get("https://geobosques.minam.gob.pe/geobosque/descargas_geobosque/alerta/espaciales/Alertas_PNCB_shape_2026.zip", stream=True)
print("\n===== Geobosques ATD 2026", s, ct)
# SERNANP geoservicios
show("SERNANP geoservicios", "https://geoservicios.sernanp.gob.pe/arcgis/rest/services/servicios_ogc/peru_sernanp_0102/MapServer/0/query?where=1%3D1&returnCountOnly=true&f=json", 200)
