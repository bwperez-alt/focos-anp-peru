import re, requests, io
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
paginas = [
 "https://www.datosabiertos.gob.pe/dataset/frecuencia-de-visitas-tur%C3%ADsticas-en-las-%C3%A1reas-naturales-protegidas-por-el-estado-%E2%80%93-servicio",
 "https://www.datosabiertos.gob.pe/dataset/frecuencia-de-visitas-tur%C3%ADsticas-en-las-%C3%A1reas-naturales-protegidas-por-el-estado-%E2%80%93-0",
 "https://www.datosabiertos.gob.pe/dataset/registro-de-monitoreo-de-la-deforestaci%C3%B3n-en-el-%C3%A1mbito-de-las-%C3%A1reas-naturales-protegidas-%E2%80%93",
]
for u in paginas:
    try:
        r = requests.get(u, headers=B, timeout=40); print("\n#####", r.status_code, u)
        t = r.text
        print("TITULO:", re.search(r"<title>(.*?)</title>", t, re.S).group(1).strip()[:200])
        desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
        i = desc.find("Descripción"); print("DESC:", desc[i:i+500] if i >= 0 else desc[:300])
        links = sorted(set(re.findall(r'href="([^"]+\.(?:csv|xlsx|xls|zip|json)[^"]*)"', t, re.I)))
        links = [requests.compat.urljoin(u, l) for l in links]
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

# también: búsqueda en el portal
r = requests.get("https://www.datosabiertos.gob.pe/search/type/dataset?query=visitantes%20areas%20naturales%20protegidas", headers=B, timeout=40)
print("\nBUSQUEDA", r.status_code)
for m in sorted(set(re.findall(r'href="(/dataset/[^"]+)"', r.text)))[:25]: print("  ", m)
