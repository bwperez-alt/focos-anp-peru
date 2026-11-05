import re, requests
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
base = "https://www.datosabiertos.gob.pe/group/servicio-nacional-de-%C3%A1reas-naturales-protegidas-por-el-estado-sernanp"
vistos = set()
for p in range(0, 8):
    t = requests.get(base + (f"?page={p}" if p else ""), headers=B, timeout=40).text
    ds = re.findall(r'<h2[^>]*>\s*<a href="(/dataset/[^"]+)"[^>]*>(.*?)</a>', t, re.S)
    if not ds: ds = [(h, h) for h in re.findall(r'href="(/dataset/[^"/?#]+)"', t)]
    nuevos = [d for d in ds if d[0] not in vistos]
    if not nuevos: break
    for h, n in nuevos:
        vistos.add(h); print("DS", re.sub(r"\s+", " ", re.sub("<[^>]+>", "", n)).strip()[:120], "|", h[:140])
for q in ["visitas", "turismo", "visitantes"]:
    t = requests.get(f"https://www.datosabiertos.gob.pe/search/field_tags/{q}/type/dataset?query={q}%20sernanp", headers=B, timeout=40).text
    for h in sorted(set(re.findall(r'href="(/dataset/[^"/?#]+)"', t)))[:15]: print("Q", q, h[:150])
t = requests.get("https://www.datosabiertos.gob.pe/dataset/frecuencia-de-visitas-tur%C3%ADsticas-en-las-%C3%A1reas-naturales-protegidas-por-el-estado-%E2%80%93-servicio", headers=B, timeout=40).text
txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", t))
for k in ["Modificado", "Actualizado", "Fecha", "Frecuencia", "Cobertura temporal", "Temporal"]:
    i = txt.find(k)
    if i >= 0: print("META", txt[i:i+160])
