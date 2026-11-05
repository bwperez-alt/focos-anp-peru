import re, requests
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
base = "https://www.igp.gob.pe"
h = requests.get(base + "/servicios/centro-sismologico-nacional/ultimo-sismo/sismos-reportados", headers=B, timeout=40).text
js = set(re.findall(r'/_nuxt/[A-Za-z0-9_.-]+\.js', h))
seen = set()
for _ in range(2):
    for j in list(js):
        if j in seen: continue
        seen.add(j)
        t = requests.get(base + j, headers=B, timeout=40).text
        js |= set(re.findall(r'/_nuxt/[A-Za-z0-9_.-]+\.js', t)) | set("/_nuxt/" + x for x in re.findall(r'"\./([A-Za-z0-9_.-]+\.js)"', t))
        for m in set(re.findall(r'https?://[a-zA-Z0-9.-]*igp[a-zA-Z0-9./_-]*', t)):
            print("URL", j, m)
        for m in set(re.findall(r'["`](/api/[^"`]{0,80})["`]', t)):
            print("API", j, m)
print("bundles", len(seen))
w = requests.get("https://api.waqi.info/map/bounds/?latlng=-12.4,-77.3,-11.7,-76.7&token=demo", headers=B, timeout=30)
print("\nWAQI bounds demo:", w.status_code, w.text[:500])
r = requests.get("https://portal.indeci.gob.pe/emergencias/feed/", headers=B, timeout=30)
print("\nRSS", r.status_code, r.headers.get("content-type"), r.text[:1500])
r = requests.get("https://portal.indeci.gob.pe/wp-json/wp/v2/emergencias?per_page=3", headers=B, timeout=30)
print("\nWPJSON", r.status_code, r.text[:600])
