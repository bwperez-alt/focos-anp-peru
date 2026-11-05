import re, requests, io
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
paginas = [
 "https://datosabiertos.gob.pe/dataset/frecuencia-de-visitas-tur%C3%ADsticas-en-las-%C3%A1reas-naturales-protegidas-por-el-estado-%E2%80%93-servicio",
 "https://datosabiertos.gob.pe/dataset/frecuencia-de-visitas-tur%C3%ADsticas-en-las-%C3%A1reas-naturales-protegidas-por-el-estado-%E2%80%93-0",
 "https://datosabiertos.gob.pe/dataset/registro-de-monitoreo-de-la-deforestaci%C3%B3n-en-el-%C3%A1mbito-de-las-%C3%A1reas-naturales-protegidas-%E2%80%93",
]
for u in paginas:
    try:
        r = requests.get(u, headers=B, timeout=40); print("\n#####", r.status_code, u)
        t = r.text
        print("TITULO:", re.search(r"<title>(.*?)</title>", t, re.S).group(1).strip()[:200])
        desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
        i = desc.find("Descripción"); print("DESC:", desc[i:i+500] if i >= 0 else desc[:300])
        links = sorted(set(re.findall(r'href="([^"]+\.(?:csv|xlsx|xls|zip|json)[^"]*)"', t, re.I)))
        for l in links[:15]: print("  RECURSO:", l)
        for l in links[:3]:
            try:
                x = requests.get(l, headers=B, timeout=60)
                print("  --", l, x.status_code, x.headers.get("content-type"), len(x.content))
                if l.lower().endswith(".csv"):
                    for enc in ("utf-8", "latin-1"):
                        try:
                            txt = x.content.decode(enc); break
                        except Exception: pass
                    print("\n".join(txt.splitlines()[:6]))
                    print("  filas:", len(txt.splitlines()))
            except Exception as e: print("  ERR", e)
    except Exception as e:
        print("ERR", u, e)
for t in ["00N_080W", "10S_080W", "00N_070W", "10S_070W"]:
    for ver in ["GFC-2024-v1.12", "GFC-2025-v1.13"]:
        u = f"https://storage.googleapis.com/earthenginepartners-hansen/{ver}/Hansen_{ver}_lossyear_{t}.tif"
        try:
            r = requests.head(u, timeout=30); print("HANSEN", ver, t, r.status_code, r.headers.get("content-length"))
        except Exception as e: print("HANSEN ERR", e)
r = requests.get("https://api.open-meteo.com/v1/forecast?latitude=-12.8&longitude=-69.3&daily=precipitation_sum,temperature_2m_max,temperature_2m_min,wind_gusts_10m_max,uv_index_max,precipitation_probability_max&forecast_days=3&timezone=America/Lima", timeout=30)
print("\nOPENMETEO", r.status_code, r.text[:600])
