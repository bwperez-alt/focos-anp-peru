"""Captura de la plataforma en vivo para el video tutorial (1920x1080)."""
import json, time
from playwright.sync_api import sync_playwright

URL = "https://bwperez-alt.github.io/focos-anp-peru/"
OUT = "capturas"
log = {}

MARCA = """(sel) => { document.querySelectorAll('.__marca').forEach(e => e.classList.remove('__marca'));
  if (!document.getElementById('__st')) { const s = document.createElement('style'); s.id='__st';
    s.textContent = '.__marca{outline:3px solid #ff6b2c!important;outline-offset:4px!important;border-radius:8px;box-shadow:0 0 0 9999px rgba(0,0,0,.0)}'; document.head.appendChild(s); }
  if (sel) { const e = document.querySelector(sel); if (e) e.classList.add('__marca'); } }"""

def main():
    import os; os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 810}, device_scale_factor=4/3, locale="es-PE", timezone_id="America/Lima")
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        n = [0]
        def foto(nombre, marca=None, espera=600):
            pg.evaluate(MARCA, marca); pg.wait_for_timeout(espera)
            n[0] += 1; f = f"{OUT}/{n[0]:02d}_{nombre}.jpg"
            pg.screenshot(path=f, type="jpeg", quality=92); log[f] = marca
        def ir(sel, off=-70):
            pg.evaluate("([s,o]) => { const e=document.querySelector(s); window.scrollTo(0, e.getBoundingClientRect().top + scrollY + o); }", [sel, off]); pg.wait_for_timeout(700)
        def mapa_listo():
            pg.wait_for_function("() => { const c=document.querySelector('#map canvas'); return c && c.width>0; }", timeout=60000); pg.wait_for_timeout(5000)

        pg.goto(URL, wait_until="networkidle"); mapa_listo()
        foto("portada")
        pg.click("#guia summary"); foto("guia", "#guia")
        pg.click("#guia summary")
        ir(".tiempo", -80); foto("selector_7d", ".tiempo")
        ir(".mapcard", -150); foto("mapa_7d", ".mapcard .filters")
        pg.click('#ventana button[data-v="24h"]') if pg.is_visible('#ventana button[data-v="24h"]') else None
        ir(".tiempo", -80); pg.click('#ventana button[data-v="24h"]'); pg.wait_for_timeout(1500); foto("kpis_24h", "#kpis")
        pg.click('#ventana button[data-v="7d"]'); pg.wait_for_timeout(1000)
        # densidad 2020–hoy en el mapa, centrado en la Amazonía sur
        ir(".mapcard", -150)
        pg.click('.chip[data-capa="densidad"]'); pg.wait_for_timeout(800)
        pg.evaluate("() => window.__mapa && 0")
        foto("mapa_densidad", '.chip[data-capa="densidad"]', 2500)
        pg.click('.chip[data-capa="densidad"]')
        # ficha Otishi
        pg.goto(URL + "#ficha-parque-nacional-otishi", wait_until="networkidle"); pg.wait_for_timeout(4000)
        ir("#fichas", -60); foto("ficha_otishi", ".interp")
        ir("#ficha .fcols", -120); foto("ficha_otishi_fuego", "#ficha .fcols > div:last-child")
        pg.goto(URL, wait_until="networkidle"); pg.wait_for_timeout(3000)
        ir("#fuego", -60); foto("fuego_rankings", "#densFuego")
        ir("#historico", -60); foto("serie_rango", "#histCtx")
        pg.click('#histRapido button[data-v="temporada"]'); pg.wait_for_timeout(800); ir("#historico", -60); foto("serie_temporada", "#histLect")
        pg.click('#histRapido button[data-v="todo"]'); pg.wait_for_timeout(800)
        ir("#histHeat", -200); foto("serie_matriz", "#histHeat")
        pg.click('#histRapido button[data-v="12m"]'); pg.wait_for_timeout(500)
        ir("#histTabla", -230); foto("serie_tabla", "#histOrden")
        ir("#docentes", -60); foto("docentes", ".practicas")
        ir("#descargaForm", -170)
        opts = pg.eval_on_selector_all("#dlArea option", "o => o.map(x => x.value)")
        if "Parque Nacional Otishi" in opts: pg.select_option("#dlArea", "Parque Nacional Otishi")
        foto("descarga", "#descargaForm")
        ir("#params", -260); foto("cita_parametros", "#params")
        pg.click("#tema"); pg.wait_for_timeout(500); pg.evaluate("window.scrollTo(0,0)"); pg.wait_for_timeout(2500); foto("modo_claro", "#tema")
        log["_errores"] = errs
        log["_estado"] = pg.inner_text("#stamp")
        b.close()
    json.dump(log, open(f"{OUT}/log.json", "w"), ensure_ascii=False, indent=1)

main()
