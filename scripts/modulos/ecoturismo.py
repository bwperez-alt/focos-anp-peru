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
    ],
}


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

    filas = []
    for tipo, capa in capas_anp[:2]:  # ANP de administración nacional y zonas reservadas
        for it in capa.items:
            nom = it["nombre"]
            lo = float(np.mean([(p[2][0] + p[3][0]) / 2 for p in it["partes"]]))
            la = float(np.mean([(p[2][1] + p[3][1]) / 2 for p in it["partes"]]))
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
            filas.append({"area": nom, "categoria": it["extra"].get("cat") or tipo, "codigo": it["extra"].get("codi", ""),
                          "lon": round(lo, 3), "lat": round(la, 3), "nivel": nivel, "motivos": motivos, **m})

    orden = {"Alerta": 0, "Atención": 1, "Normal": 2}
    filas.sort(key=lambda r: (orden[r["nivel"]], -r["fuego_anp_7d"], r["area"]))
    res = {"generado": datetime.now(timezone.utc).isoformat(timespec="minutes"), "reglas": REGLAS,
           "conteo": {k: sum(1 for f in filas if f["nivel"] == k) for k in orden}, "areas": filas}
    (salida / "ecoturismo.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":"), default=str))
    return {"registros": len(filas), "ultimo_dato": res["generado"][:16].replace("T", " ")}
