"""Ecoturismo: semáforo de condiciones por Área Natural Protegida.

Integra los demás módulos (fuego, emergencias INDECI, sismos, calidad del aire y deforestación)
en un nivel de atención por ANP pensado para visitantes, operadores e investigadores.
Las reglas son explícitas y están en REGLAS para que puedan citarse y ajustarse.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REGLAS = {
    "Alerta": [
        "3 o más focos de calor dentro del ANP en las últimas 72 h",
        "Incendio forestal reportado por INDECI en un distrito cuyo centroide cae dentro del ANP (últimos 7 días)",
        "Sismo de magnitud ≥ 6,5 a menos de 100 km en las últimas 72 h",
    ],
    "Atención": [
        "Al menos un foco de calor dentro del ANP en los últimos 7 días",
        "5 o más focos en la zona de amortiguamiento en los últimos 7 días",
        "Otra emergencia INDECI dentro del ANP, o cualquier emergencia en su zona de amortiguamiento (últimos 7 días)",
        "Sismo de magnitud ≥ 5,0 a menos de 100 km en los últimos 7 días",
        "PM2,5 (24 h) sobre el ECA en una estación a menos de 30 km",
        "PM2,5 (24 h) estimado por el modelo CAMS sobre el ECA (50 µg/m³) en el área",
        "Pronóstico de lluvia fuerte (≥ 30 mm/día), tormenta o ráfagas ≥ 60 km/h hoy o mañana",
    ],
}

# ------------------------------------------------------------------ recomendaciones para visitantes
BASE_COMUN = [
    ("Visita", "Regístrate en el puesto de control y respeta la zonificación y los senderos autorizados."),
    ("Residuos", "Lleva de regreso todos tus residuos; no dejes restos de comida ni plásticos."),
    ("Fauna", "No alimentes ni te acerques a la fauna silvestre; no extraigas plantas, animales ni restos arqueológicos."),
]
BASE_ECO = {
    "marino-costero": [("Mar", "Respeta la distancia a aves y lobos marinos; en embarcaciones usa chaleco salvavidas."),
                       ("Sol", "Radiación y viento intensos en la costa: protector solar, gorra e hidratación.")],
    "costa": [("Calor", "Ambiente seco: lleva agua suficiente y evita las horas de mayor sol."),
              ("Senderos", "Terreno arenoso o pedregoso: calzado cerrado y no salgas de los senderos.")],
    "altoandino": [("Altura", "Más de 3 000 m: aclimátate, camina despacio y evita esfuerzos el primer día."),
                   ("Frío", "Fuertes cambios de temperatura: abrigo por capas, guantes y protección solar alta.")],
    "montaña": [("Clima", "Clima cambiante de montaña: lleva impermeable y abrigo ligero."),
                ("Pendientes", "Senderos empinados y húmedos: bastones y calzado con buen agarre.")],
    "amazonía": [("Salud", "Repelente, ropa de manga larga y vacuna contra la fiebre amarilla recomendada por el MINSA."),
                 ("Ríos", "Desplázate en ríos solo con operadores autorizados y chaleco salvavidas.")],
}


def ecosistema(categoria: str, nombre: str, elev, lon) -> str:
    n = (categoria + " " + nombre).lower()
    if any(k in n for k in ("mar ", "islas", "islotes", "dorsal", "paracas", "manglares", "lagunas de mejía", "pantanos", "punta ")) or (elev is not None and elev <= 5):
        return "marino-costero"
    if elev is not None and elev >= 3000:
        return "altoandino"
    if lon is not None and lon >= -77.8 and (elev is None or elev < 1200):
        return "amazonía"
    if elev is not None and elev >= 1200:
        return "montaña"
    return "costa"


def recomendaciones(m: dict, clima_a: dict | None, vis_a: dict | None, eco: str, mes: int) -> list[dict]:
    """Recomendaciones dinámicas (según condiciones actuales) seguidas de las de base."""
    r = []
    def add(tema, texto, motivo, nivel="info"):
        r.append({"tema": tema, "texto": texto, "motivo": motivo, "nivel": nivel, "tipo": "dinamica"})
    if m.get("incendio_anp") or m.get("fuego_anp_72h", 0) >= 1:
        add("Fuego", "Hay fuego activo en el área: no ingreses a zonas con humo, no enciendas fogatas y reporta cualquier incendio al guardaparque o a los bomberos (116).",
            f"{m.get('fuego_anp_7d', 0)} focos de calor en 7 días" + (" e incendio reportado por INDECI" if m.get("incendio_anp") else ""), "alta")
    elif m.get("fuego_za_7d", 0) >= 1:
        add("Fuego", "Hay quemas en el entorno del área: evita encender fuego y consulta el estado de los accesos antes de ir.",
            f"{m['fuego_za_7d']} focos en la zona de amortiguamiento (7 días)", "media")
    pm = m.get("pm25_24h") if m.get("pm25_24h") is not None else m.get("pm25_modelo_24h")
    if pm is not None and pm > 50:
        add("Aire", "Calidad del aire mala: evita actividad física intensa al aire libre; personas con asma, niños y adultos mayores deberían postergar la visita o usar mascarilla.",
            f"PM2,5 de {pm} µg/m³ en 24 h (ECA 50)", "alta")
    elif pm is not None and pm > 15:
        add("Aire", "Calidad del aire moderada: las personas sensibles deberían reducir los esfuerzos prolongados.",
            f"PM2,5 de {pm} µg/m³ en 24 h (guía OMS 15)", "baja")
    if clima_a:
        dias = clima_a.get("dias", [])[:2]
        av = {a for d in dias for a in d.get("avisos", [])}
        cuando = lambda clave: " y ".join(("hoy" if i == 0 else "mañana") for i, d in enumerate(dias) if clave in d.get("avisos", []))
        if "lluvia_fuerte" in av or "tormenta" in av:
            mm = max((d.get("lluvia_mm") or 0) for d in dias)
            add("Lluvia", "Lluvia fuerte prevista: evita cauces, quebradas y laderas inestables (riesgo de huaicos y crecidas); confirma que los accesos estén abiertos.",
                f"Hasta {mm:.0f} mm/día {cuando('lluvia_fuerte') or cuando('tormenta')}", "alta")
        elif "lluvia_moderada" in av:
            add("Lluvia", "Lluvia prevista: lleva impermeable y ten cuidado con senderos resbaladizos.", f"Lluvia moderada {cuando('lluvia_moderada')}", "baja")
        if "helada" in av:
            tmin = min(d["tmin"] for d in dias if d.get("tmin") is not None)
            add("Helada", "Temperaturas bajo cero: ropa térmica, saco de dormir adecuado y cuidado con superficies congeladas.", f"Mínima de {tmin:.0f} °C {cuando('helada')}", "media")
        if "calor" in av:
            tmax = max(d["tmax"] for d in dias if d.get("tmax") is not None)
            add("Calor", "Calor intenso: hidrátate con frecuencia y evita caminar entre las 11:00 y las 15:00.", f"Máxima de {tmax:.0f} °C {cuando('calor')}", "media")
        if "viento" in av:
            add("Viento", "Ráfagas fuertes: precaución en miradores, acantilados y embarcaciones.", f"Ráfagas de {max((d.get('rafaga_kmh') or 0) for d in dias):.0f} km/h", "media")
        if "uv_extremo" in av:
            add("UV", "Radiación UV extrema: protector FPS 50+, sombrero de ala ancha y lentes con filtro; busca sombra al mediodía.", f"Índice UV {max((d.get('uv') or 0) for d in dias):.0f}", "media")
        elif "uv_muy_alto" in av:
            add("UV", "Radiación UV muy alta: usa protector solar y gorra.", f"Índice UV {max((d.get('uv') or 0) for d in dias):.0f}", "baja")
    if m.get("sismo_max") and m["sismo_max"] >= 5:
        add("Sismo", "Hubo actividad sísmica reciente cerca: identifica rutas de evacuación y evita zonas con riesgo de derrumbes.", f"Sismo M{m['sismo_max']:.1f} a menos de 100 km (7 días)", "media")
    if m.get("emerg_anp", 0) > m.get("incendio_anp", 0) or m.get("emerg_za"):
        add("Emergencia", "INDECI reporta emergencias en el área o su entorno: consulta a la jefatura del ANP antes de viajar.", ", ".join(m.get("emerg_tipos", [])) or "Reporte del COEN", "media")
    if vis_a and mes in vis_a.get("meses_pico_num", []):
        add("Afluencia", "Temporada de mayor afluencia: reserva con anticipación, llega temprano y respeta los aforos.",
            f"Meses de más visitas: {', '.join(vis_a.get('meses_pico', []))} ({'MINCETUR/SERNANP' if 'ultimo' in vis_a else 'SERNANP'})", "baja")
    for tema, texto in BASE_ECO.get(eco, []) + BASE_COMUN:
        r.append({"tema": tema, "texto": texto, "motivo": None, "nivel": "base", "tipo": "base"})
    return r


def _leer(p: Path, defecto):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return defecto


def km(lon1, lat1, lon2, lat2):
    return np.hypot((lon2 - lon1) * 111.32 * np.cos(np.radians(lat1)), (lat2 - lat1) * 110.57)


def ejecutar(salida: Path, capas_anp) -> dict:
    ahora = pd.Timestamp.now(tz="America/Lima").tz_localize(None)
    focos = _leer(salida / "focos.geojson", {"features": []})["features"]
    fdf = pd.DataFrame([{**f["properties"], "lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1]} for f in focos])
    if not fdf.empty:
        fdf["t"] = pd.to_datetime(fdf.f)
    riesgos = _leer(salida / "riesgos.json", {})
    emerg = pd.DataFrame(riesgos.get("emergencias", []))
    if not emerg.empty:
        emerg["t"] = pd.to_datetime(emerg.publicado)
    sismos = pd.DataFrame(riesgos.get("sismos", []))
    if not sismos.empty:
        sismos["t"] = pd.to_datetime(sismos.t)
    aire = _leer(salida / "aire.json", {}).get("estaciones", [])
    aire_mod = {r["area"]: r for r in _leer(salida / "aire_modelo.json", {}).get("areas", [])}
    defo = {(r["area"], r["zona"]): r for r in _leer(salida / "deforestacion.json", {}).get("ranking_areas", [])}
    clima = {r["area"]: r for r in _leer(salida / "clima.json", {}).get("areas", [])}
    vis = _leer(salida / "visitas.json", {}).get("areas", {})
    vis_act = _leer(salida / "visitas_actual.json", {}).get("sitios", {})
    mes = ahora.month

    filas = []
    from .aire_modelo import agrupar_anp
    for g in agrupar_anp(capas_anp):  # ANP de administración nacional y zonas reservadas
        if True:
            it = {"nombre": g["area"], "extra": {"cat": g["categoria"], "codi": g["codigo"]}}
            tipo = g["categoria"]
            nom, lo, la = g["area"], g["lon"], g["lat"]
            m = {"fuego_anp_72h": 0, "fuego_anp_7d": 0, "fuego_za_7d": 0, "emerg_anp": 0, "emerg_za": 0,
                 "sismo_max": None, "pm25_24h": None, "deforestacion_90d": 0}
            motivos, nivel = [], "Normal"
            if not fdf.empty:
                dentro = fdf[(fdf.a == nom) & (fdf.z == "Dentro de ANP")]
                m["fuego_anp_72h"] = int((dentro.t > ahora - timedelta(hours=72)).sum())
                m["fuego_anp_7d"] = int(len(dentro))
                m["fuego_za_7d"] = int(((fdf.a == nom) & (fdf.z == "Zona de amortiguamiento")).sum())
            if not emerg.empty and "area" in emerg:
                rec = emerg[(emerg.area == nom) & (emerg.t > ahora - timedelta(days=7))]
                m["emerg_anp"] = int((rec.zona == "Dentro de ANP").sum())
                m["incendio_anp"] = int(((rec.zona == "Dentro de ANP") & rec.tipo.fillna("").str.lower().str.startswith("incendio forestal")).sum())
                m["emerg_za"] = int((rec.zona == "Zona de amortiguamiento").sum())
                m["emerg_tipos"] = sorted(set(rec.tipo.dropna()))
            if not sismos.empty:
                d = km(lo, la, sismos.lon.to_numpy(), sismos.lat.to_numpy())
                cerca = sismos[(d < 100)]
                if len(cerca):
                    s72 = cerca[cerca.t > ahora - timedelta(hours=72)]
                    s7 = cerca[cerca.t > ahora - timedelta(days=7)]
                    m["sismo_max"] = float(s7.mag.max()) if len(s7) else None
                    if len(s72) and s72.mag.max() >= 6.5:
                        nivel = "Alerta"; motivos.append(f"Sismo M{s72.mag.max():.1f} a menos de 100 km (72 h)")
                    elif len(s7) and s7.mag.max() >= 5.0:
                        motivos.append(f"Sismo M{s7.mag.max():.1f} a menos de 100 km (7 días)")
                        nivel = "Atención" if nivel == "Normal" else nivel
            for e in aire:
                if km(lo, la, e["lon"], e["lat"]) < 30:
                    pm = (e.get("valores", {}).get("PM2.5") or {}).get("prom_24h")
                    if pm is not None:
                        m["pm25_24h"] = max(m["pm25_24h"] or 0, pm)
            am = aire_mod.get(nom, {})
            m["pm25_modelo_24h"] = am.get("pm2_5_24h")
            m["deforestacion_90d"] = int(defo.get((nom, "Dentro de ANP"), {}).get("ultimos_90d", 0))

            if m["fuego_anp_72h"] >= 3:
                nivel = "Alerta"; motivos.insert(0, f"{m['fuego_anp_72h']} focos de calor dentro del área (72 h)")
            elif m["fuego_anp_7d"] >= 1:
                nivel = "Atención" if nivel == "Normal" else nivel; motivos.insert(0, f"{m['fuego_anp_7d']} foco{'s' if m['fuego_anp_7d'] != 1 else ''} de calor dentro del área (7 días)")
            if m.get("incendio_anp"):
                nivel = "Alerta"; motivos.append("Incendio forestal reportado por INDECI dentro del área")
            if m["emerg_anp"] > m.get("incendio_anp", 0):
                nivel = "Atención" if nivel == "Normal" else nivel; motivos.append(f"Emergencia INDECI dentro del área: {', '.join(t for t in m.get('emerg_tipos', []) if not t.lower().startswith('incendio forestal')) or 'ver reportes'}")
            elif m["emerg_za"]:
                nivel = "Atención" if nivel == "Normal" else nivel; motivos.append(f"Emergencia INDECI en la zona de amortiguamiento: {', '.join(m.get('emerg_tipos', []))}")
            if m["fuego_za_7d"] >= 5:
                nivel = "Atención" if nivel == "Normal" else nivel; motivos.append(f"{m['fuego_za_7d']} focos en la zona de amortiguamiento (7 días)")
            if m["pm25_24h"] is not None and m["pm25_24h"] > 50:
                nivel = "Atención" if nivel == "Normal" else nivel; motivos.append(f"PM2,5 de {m['pm25_24h']} µg/m³ en 24 h (sobre el ECA)")
            if m["pm25_modelo_24h"] is not None and m["pm25_modelo_24h"] > 50:
                nivel = "Atención" if nivel == "Normal" else nivel; motivos.append(f"PM2,5 estimado (CAMS) de {m['pm25_modelo_24h']} µg/m³ en 24 h (sobre el ECA)")
            ca = clima.get(nom)
            if ca:
                dias = ca.get("dias", [])[:2]
                av = {a for d in dias for a in d.get("avisos", [])}
                if av & {"lluvia_fuerte", "tormenta", "viento"}:
                    nivel = "Atención" if nivel == "Normal" else nivel
                    partes = []
                    if "lluvia_fuerte" in av: partes.append(f"lluvia fuerte ({max((d.get('lluvia_mm') or 0) for d in dias):.0f} mm/día)")
                    if "tormenta" in av: partes.append("tormenta")
                    if "viento" in av: partes.append(f"ráfagas de {max((d.get('rafaga_kmh') or 0) for d in dias):.0f} km/h")
                    motivos.append("Pronóstico para hoy o mañana: " + ", ".join(partes))
            va = vis_act.get(nom) or vis.get(nom) or next((v for k, v in vis.items() if nom.startswith(k)), None)
            cat = it["extra"].get("cat") or tipo
            eco = ecosistema(cat, nom, (ca or {}).get("elevacion"), lo)
            filas.append({"area": nom, "categoria": cat, "codigo": it["extra"].get("codi", ""), "departamentos": g.get("departamentos", ""),
                          "lon": round(lo, 3), "lat": round(la, 3), "nivel": nivel, "motivos": motivos, "ecosistema": eco,
                          "elevacion": (ca or {}).get("elevacion"), "temporada_alta": bool(va and mes in va.get("meses_pico_num", [])),
                          "recomendaciones": recomendaciones(m, ca, va, eco, mes), **m})

    orden = {"Alerta": 0, "Atención": 1, "Normal": 2}
    filas.sort(key=lambda r: (orden[r["nivel"]], -r["fuego_anp_7d"], r["area"]))
    res = {"generado": datetime.now(timezone.utc).isoformat(timespec="minutes"), "reglas": REGLAS,
           "conteo": {k: sum(1 for f in filas if f["nivel"] == k) for k in orden}, "areas": filas}
    (salida / "ecoturismo.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":"), default=str))
    return {"registros": len(filas), "ultimo_dato": res["generado"][:16].replace("T", " ")}
