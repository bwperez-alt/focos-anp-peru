import re, requests
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
base = "https://datosturismo.mincetur.gob.pe"
s = requests.Session(); s.headers.update(B)
r = s.get(base + "/appdatosturismo/frmReporte.aspx?id=229", timeout=60); t = r.text
m = re.search(r'(/appDatosTurismo/Reserved\.ReportViewerWebControl\.axd\?Culture=[^"\']*?OpType=Export[^"\']*?Format=)', t)
x = s.get(base + m.group(1).replace("\\u0026", "&") + "CSV", timeout=60)
print("ERR500:", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x.text))[:1200])
# formulario: campos ocultos y botones
for n, v in re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]{0,80})', t)[:40]: print("  input", n, v[:60])
for n in re.findall(r'<input[^>]*type="submit"[^>]*name="([^"]+)"', t): print("  submit", n)
print("  form action:", re.findall(r'<form[^>]*action="([^"]+)"', t))
i = t.find("ReportViewer1"); print("\nRV snippet:", re.sub(r"\s+", " ", t[i:i+1500]))
print("\nnúmeros en página:", re.findall(r">\s*(\d{1,3}(?:[.,]\d{3})+)\s*<", t)[:20])
# Postback simulando 'Ver reporte'
data = {k: v for k, v in re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', t)}
data.update({"ddlINICIO": "2024", "ddlINICIOMES": "1", "ddlFIN": "2026", "ddlFINMES": "12"})
for b in re.findall(r'<input[^>]*type="submit"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', t): data[b[0]] = b[1]
y = s.post(base + "/appdatosturismo/frmReporte.aspx?id=229", data=data, timeout=90)
print("\nPOSTBACK", y.status_code, len(y.text)); print("números:", re.findall(r">\s*(\d{1,3}(?:[.,]\d{3})+)\s*<", y.text)[:30])
m2 = re.search(r'(/appDatosTurismo/Reserved\.ReportViewerWebControl\.axd\?Culture=[^"\']*?OpType=Export[^"\']*?Format=)', y.text)
if m2:
    z = s.get(base + m2.group(1).replace("\\u0026", "&") + "CSV", timeout=90)
    print("EXPORT tras postback", z.status_code, z.headers.get("content-type"), len(z.content)); print(z.content[:1500].decode("utf-8", "replace"))
for op in ["ReportArea", "Visible"]:
    pass
