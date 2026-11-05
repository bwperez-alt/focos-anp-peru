import re, requests
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
base = "https://datosturismo.mincetur.gob.pe/appdatosturismo/"
for js in ["js/reportes.js", "js/capitulo24.js", "js/application.js", "js/utilitarios.js", "js/peru.js"]:
    t = requests.get(base + js, headers=B, timeout=40).text
    print("\n#####", js, len(t))
    for m in re.finditer(r"(url\s*[:=]|\.ajax|getJSON|\.post|\.get\(|traerRutaAplicacion|ruta|Ruta|\.aspx|\.asmx|\.svc|/api/|WebMethod|ficha|Ficha)", t):
        a = max(0, m.start() - 160); print("  ..", t[a:m.start() + 260].replace("\n", " ")); 
