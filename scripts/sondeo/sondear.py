import re, requests
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
base = "http://datosturismo.mincetur.gob.pe/appdatosturismo/"
for u in [base + "content2.html", base + "Content2.html", base + "content1.html", "https://datosturismo.mincetur.gob.pe/appdatosturismo/content2.html"]:
    try:
        r = requests.get(u, headers=B, timeout=40)
        print("\n#####", r.status_code, u, len(r.text))
        t = r.text
        print(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))[:1500])
        for m in sorted(set(re.findall(r'(?:href|src|url)\s*[:=]\s*["\']([^"\']+)["\']', t)))[:80]:
            print("  ref:", m)
        for m in sorted(set(re.findall(r'["\']([^"\']*(?:\.xlsx?|\.csv|\.json|\.php|\.aspx|/api/)[^"\']*)["\']', t)))[:40]:
            print("  data:", m)
    except Exception as e:
        print("ERR", u, e)
