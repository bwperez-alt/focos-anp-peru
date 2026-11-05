import re, requests, io
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
base = "https://datosturismo.mincetur.gob.pe"
def bajar(rid, ini="2019", fin="2026", fmt="EXCEL"):
    s = requests.Session(); s.headers.update(B)
    u = base + f"/appdatosturismo/frmReporte.aspx?id={rid}"
    t = s.get(u, timeout=60).text
    data = dict(re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', t))
    data.update({"ddlINICIO": ini, "ddlINICIOMES": "1", "ddlFIN": fin, "ddlFINMES": "12", "btnGenerarReporte": "Ver reporte"})
    t2 = s.post(u, data=data, timeout=90).text
    m = re.search(r'(/appDatosTurismo/Reserved\.ReportViewerWebControl\.axd\?Culture=[^"\']*?OpType=Export[^"\']*?Format=)', t2)
    x = s.get(base + m.group(1).replace("\\u0026", "&") + fmt, timeout=120)
    return x
for fmt in ["EXCEL"]:
    x = bajar("229", fmt=fmt)
    print("\n#####", fmt, x.status_code, x.headers.get("content-type"), len(x.content), x.headers.get("content-disposition"))
    if x.status_code == 200 and fmt == "EXCEL":
        import pandas as pd
        xl = pd.read_excel(io.BytesIO(x.content), header=None, engine="xlrd")
        for i, row in xl.iterrows():
            vals = [str(v)[:40] for v in row.tolist() if str(v) != "nan"]
            if vals: print(i, " | ".join(vals))
