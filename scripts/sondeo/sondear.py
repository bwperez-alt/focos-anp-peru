import re, requests
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
base = "https://datosturismo.mincetur.gob.pe/appdatosturismo/"
t = requests.get(base + "js/reportes.js", headers=B, timeout=40).text
i = t.find("var capitulo2"); j = t.find("]", i)
print("CAP2:", t[i:j+1].replace("\n", " ")[:6000])
print("\nRESTO reportes:", re.sub(r"\s+", " ", t[j+1:])[:2500])
for js in ["js/capitulo24.js", "js/application.js", "js/utilitarios.js"]:
    x = requests.get(base + js, headers=B, timeout=40).text
    print("\n#####", js, len(x)); print(re.sub(r"\s+", " ", x)[:3000])
h = requests.get(base + "content2.html", headers=B, timeout=40).text
k = h.find("strRutaAplicacionMaster"); print("\nHTML SCRIPT:", re.sub(r"\s+", " ", h[k-200:k+3000]))
