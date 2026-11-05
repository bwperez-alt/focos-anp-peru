import re, requests, html
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
base = "https://datosturismo.mincetur.gob.pe"
for rid in ["229", "203", "241"]:
    s = requests.Session(); s.headers.update(B)
    r = s.get(base + f"/appdatosturismo/frmReporte.aspx?id={rid}", timeout=60)
    t = r.text
    m = re.search(r'(/appDatosTurismo/Reserved\.ReportViewerWebControl\.axd\?Culture=[^"\']*?OpType=Export[^"\']*?Format=)', t)
    print("\n#####", rid, r.status_code, bool(m))
    sel = re.findall(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', t, re.S)
    for n, body in sel:
        print("  select", n, "->", re.findall(r'<option[^>]*selected[^>]*value="([^"]*)"|<option[^>]*value="([^"]*)"[^>]*selected', body)[:2])
    if not m: continue
    url = base + m.group(1).replace("\\u0026", "&")
    for fmt in ["CSV", "EXCELOPENXML", "XML"]:
        x = s.get(url + fmt, timeout=90)
        print("  FORMAT", fmt, x.status_code, x.headers.get("content-type"), len(x.content))
        if fmt in ("CSV", "XML") and x.status_code == 200:
            for enc in ("utf-8-sig", "utf-16", "latin-1"):
                try: tx = x.content.decode(enc); break
                except Exception: pass
            print("\n".join(tx.splitlines()[:30])); print("  ...", len(tx.splitlines()), "líneas"); print("\n".join(tx.splitlines()[-8:]))
            break
