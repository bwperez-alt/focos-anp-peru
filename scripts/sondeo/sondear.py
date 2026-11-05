import requests
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
for tag, u in [("VIS", "https://www.datosabiertos.gob.pe/sites/default/files/SERNANPdataset_Turismo.csv"),
               ("DEF", "https://www.datosabiertos.gob.pe/sites/default/files/Dataset_DeforestacionAnp_SERNANP.csv")]:
    c = requests.get(u, headers=B, timeout=60).content
    for enc in ("utf-8-sig", "latin-1"):
        try: t = c.decode(enc); break
        except Exception: pass
    for l in t.splitlines(): print(tag + "|" + l)
