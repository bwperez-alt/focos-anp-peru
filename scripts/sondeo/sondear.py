"""Sondeo 3: INDECI emergencias, IGP, WAQI bounds (token demo)."""
import re, requests, json
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
t = requests.get("https://portal.indeci.gob.pe/emergencias/", headers=B, timeout=40).text
txt = re.sub(r"\s+", " ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S))
print("INDECI TEXTO:", re.sub(r"<[^>]+>", " | ", txt)[:6000])
for m in sorted(set(re.findall(r'href="([^"]+)"', t)))[:120]:
    if re.search(r"emergen|reporte|incendio|pdf|sinpad|json|api", m, re.I): print("  link:", m)
r = requests.get("https://www.igp.gob.pe/servicios/centro-sismologico-nacional/ultimo-sismo/sismos-reportados", headers=B, timeout=40).text
print("\nIGP:", r[:1500])
for u in sorted(set(re.findall(r'(?:src|href)="([^"]+\.js)"', r)))[:10]:
    print("  js:", u)
for api in ["https://api.igp.gob.pe/", "https://www.igp.gob.pe/api/sismos", "https://ultimosismo.igp.gob.pe/api/ultimo-sismo/ajaxb/2026"]:
    try:
        x = requests.get(api, headers=B, timeout=20); print("\nAPI", api, x.status_code, x.text[:300])
    except Exception as e: print("\nAPI", api, "ERR", str(e)[:150])
w = requests.get("https://api.waqi.info/map/bounds/?latlng=-12.4,-77.3,-11.7,-76.7&token=demo", headers=B, timeout=30)
print("\nWAQI bounds demo:", w.status_code, w.text[:800])
