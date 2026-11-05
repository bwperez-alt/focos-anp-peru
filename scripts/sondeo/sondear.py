import re, requests, io
import pandas as pd
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
base = "https://datosturismo.mincetur.gob.pe"
js = requests.get(base + "/appdatosturismo/js/reportes.js", headers=B, timeout=40).text
i = js.find("var capitulo2"); j = js.find("];", i)
for m in re.finditer(r'codigo\s*:\s*"(\d+)"\s*,\s*titulo\s*:\s*[\'"]([^\'"]+)[\'"]\s*,\s*departamento\s*:\s*"([^"]*)"', js[i:j]):
    if re.search(r"Parque Nacional|Reserva|Santuario|Islas|Bosque|Refugio|Lomas|Pantanos|Manglares|Colca|Coto", m.group(2), re.I):
        print("ANP", m.groups())
def bajar(rid, ini="2024", fin="2026"):
    s = requests.Session(); s.headers.update(B)
    u = base + f"/appdatosturismo/frmReporte.aspx?id={rid}"
    t = s.get(u, timeout=60).text
    data = dict(re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', t))
    sel = dict(re.findall(r'<select[^>]*name="([^"]+)"', t) and [(n, "") for n in re.findall(r'<select[^>]*name="([^"]+)"', t)])
    print("  selects", list(sel))
    for n in re.findall(r'<select[^>]*name="([^"]+)"', t):
        opts = re.findall(r'<option[^>]*value="([^"]*)"', t.split(f'name="{n}"')[1].split("</select>")[0])
        print("   ", n, opts[:6], "...", len(opts))
        data[n] = ("12" if "FIN" in n else "1") if "MES" in n else (fin if "FIN" in n else ini)
    data["btnGenerarReporte"] = "Ver reporte"
    for b in re.findall(r'<input[^>]*type="submit"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', t): data[b[0]] = b[1]
    t2 = s.post(u, data=data, timeout=90).text
    if "OpType=Export" not in t2: print(re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",t2))[:800])
    m = re.search(r'(/appDatosTurismo/Reserved\.ReportViewerWebControl\.axd\?Culture=[^"\']*?OpType=Export[^"\']*?Format=)', t2)
    return s.get(base + m.group(1).replace("\\u0026", "&") + "EXCEL", timeout=120)
for rid in ["310"]:
    x = bajar(rid)
    print("\n#####", rid, x.status_code, len(x.content))
    xl = pd.read_excel(io.BytesIO(x.content), header=None, engine="xlrd")
    for k, row in xl.iterrows():
        vals = [str(v)[:30] for v in row.tolist() if str(v) != "nan"]
        if vals: print(k, " | ".join(vals)[:400])
