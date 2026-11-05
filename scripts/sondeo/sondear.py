import sys, json
from pathlib import Path
sys.path.insert(0, "scripts")
import pipeline as P
from modulos import visitas_actual as V
capas, za = P.capas_territorio()
out = Path("/tmp/out"); out.mkdir(exist_ok=True)
print(V.ejecutar(out, Path("/tmp/arch"), capas))
d = json.load(open(out / "visitas_actual.json"))
print("INFO AL:", d["informacion_al"], "ULT:", d["ultimo_mes"])
for r in d["ranking"]: print("RANK", r)
for a, v in d["sitios"].items(): print("SITIO", a, "|", v["titulo_mincetur"], "|", v["serie"][0]["periodo"], "->", v["ultimo"], v["meses_pico"], v["pct_extranjeros_12m"])
print("REG", d["regiones"]["periodo"], d["regiones"]["filas"][:3], len(d["regiones"]["filas"]))
