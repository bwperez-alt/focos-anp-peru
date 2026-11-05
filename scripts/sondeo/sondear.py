"""Sondeo 2: reintentos con cabeceras de navegador y hosts alternativos."""
import requests, socket, time
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "es-PE,es;q=0.9"}
def t(nombre, u, n=300, **kw):
    t0 = time.time()
    try:
        r = requests.get(u, headers=B, timeout=25, **kw)
        print(f"\n== {nombre} {r.status_code} {r.headers.get('content-type')} {len(r.content)}B {time.time()-t0:.1f}s\n{r.text[:n]}")
    except Exception as e:
        print(f"\n== {nombre} ERR {type(e).__name__} {str(e)[:160]} {time.time()-t0:.1f}s")
for h in ["www.senamhi.gob.pe", "senamhi.gob.pe", "idesep.senamhi.gob.pe", "ultimosismos.igp.gob.pe", "www.igp.gob.pe", "geobosques.minam.gob.pe", "sinpad.indeci.gob.pe"]:
    try: print("DNS", h, socket.gethostbyname(h))
    except Exception as e: print("DNS", h, "ERR", e)
t("senamhi http", "http://www.senamhi.gob.pe/mapas/mapa-ca-monitoreo/map_data_ca.php", 120)
t("senamhi sin www", "https://senamhi.gob.pe/mapas/mapa-ca-monitoreo/map_data_ca.php", 120)
t("idesep", "http://idesep.senamhi.gob.pe/indicadores/", 200)
t("geobosques UA navegador", "https://geobosques.minam.gob.pe/geobosque/descargas_geobosque/alerta/espaciales/Alertas_PNCB_shape_2026.zip", 80, stream=True)
t("geobosques home", "https://geobosques.minam.gob.pe/geobosque/view/descargas.php", 200)
t("igp www", "https://www.igp.gob.pe/servicios/centro-sismologico-nacional/ultimo-sismo/sismos-reportados", 200)
t("indeci emergencias", "https://portal.indeci.gob.pe/emergencias/", 50)
t("waqi demo", "https://api.waqi.info/feed/@382/?token=demo", 300)
t("openaq locations peru", "https://api.openaq.org/v3/locations?countries_id=158&limit=5", 300)
