import re, requests
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
base = "https://datosturismo.mincetur.gob.pe/appdatosturismo/"
s = requests.Session(); s.headers.update(B)
for u in ["frmReporte.aspx?id=229", "sistema/frmReporte.aspx?id=229", "sistema/reporte/frmReporte.aspx?id=229",
          "sistema/default.aspx?op=reporte/frmConsReporte.aspx?grupo=SITIOS", "sistema/reporte/frmConsReporte.aspx?grupo=SITIOS"]:
    try:
        r = s.get(base + u, timeout=40)
        t = r.text
        print("\n#####", r.status_code, u, len(t), r.headers.get("content-type"))
        txt = re.sub(r"\s+", " ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S))
        print(re.sub(r"<[^>]+>", " | ", txt)[:2500])
        for m in sorted(set(re.findall(r'(?:src|href|action)="([^"]+)"', t)))[:40]: print("  ref:", m)
        for m in sorted(set(re.findall(r'["\']([^"\']*(?:\.aspx|\.asmx|\.ashx|Reserved\.ReportViewer|ReportServer)[^"\']*)["\']', t)))[:30]: print("  rpt:", m)
    except Exception as e:
        print("ERR", u, e)
