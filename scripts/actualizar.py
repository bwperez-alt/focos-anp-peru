"""Orquestador del Observatorio Ambiental de ANP del Perú.

Ejecuta cada módulo de forma independiente: si una fuente oficial no responde,
se conserva el último dato publicado y se registra el error en docs/data/estado.json.

    python scripts/actualizar.py                # todos los módulos
    python scripts/actualizar.py --solo aire    # un módulo
"""
from __future__ import annotations

import argparse
import os
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pipeline as fuego  # noqa: E402
import focos_hist  # noqa: E402
from modulos import aire, aire_modelo, clima, deforestacion, ecoturismo, riesgos, sernanp_datos, visitas_actual  # noqa: E402

SALIDA = fuego.SALIDA
ARCHIVO = fuego.ARCHIVO
ESTADO = SALIDA / "estado.json"


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="minutes")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", nargs="*", default=None)
    a = ap.parse_args()
    SALIDA.mkdir(parents=True, exist_ok=True)
    estado = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
    capas, za = fuego.capas_territorio()

    def correr(nombre, fn):
        if a.solo and nombre not in a.solo:
            return
        t0 = time.time()
        print(f"\n### {nombre}")
        previo = estado.get(nombre, {})
        try:
            r = fn() or {}
            estado[nombre] = {**previo, **r, "ok": True, "error": None, "ejecutado": ahora(), "segundos": round(time.time() - t0, 1)}
            if not r.get("omitido"):
                estado[nombre]["actualizado"] = ahora()
        except (Exception, SystemExit) as e:  # noqa: BLE001
            traceback.print_exc()
            estado[nombre] = {**previo, "ok": False, "error": f"{type(e).__name__}: {e}"[:300], "ejecutado": ahora()}
        print(f"    -> {estado[nombre]}")

    def _fuego():
        df, res = fuego.ejecutar("7d")
        return {"ultimo_dato": res["periodo"]["hasta"], "ultimo_foco": res.get("ultimo_foco"), "registros": res["totales"]["focos"]}

    correr("fuego", _fuego)
    # serie mensual 2020–hoy (carga histórica de FIRMS + archivo diario) y CSV mensuales para descargas
    correr("serie", lambda: focos_hist.construir_serie(capas))
    correr("aire", lambda: aire.ejecutar(SALIDA, ARCHIVO, token=os.environ.get("WAQI_TOKEN")))

    def _defo():
        subidos = sorted((fuego.RAIZ / "data" / "entrada").glob("Alertas_PNCB_shape_*.zip"))
        entrada = subidos[-1] if subidos else None
        anio = int(entrada.stem.split("_")[-1]) if entrada else None
        return deforestacion.ejecutar(SALIDA, ARCHIVO, capas, za, entrada=entrada, anio=anio, previo=SALIDA / "deforestacion.json")

    correr("deforestacion", _defo)
    correr("riesgos", lambda: riesgos.ejecutar(SALIDA, ARCHIVO, capas, za))
    correr("aire_modelo", lambda: aire_modelo.ejecutar(SALIDA, ARCHIVO, capas))
    correr("clima", lambda: clima.ejecutar(SALIDA, capas))
    correr("sernanp", lambda: sernanp_datos.ejecutar(SALIDA, ARCHIVO, capas))
    correr("visitas", lambda: visitas_actual.ejecutar(SALIDA, ARCHIVO, capas))
    correr("ecoturismo", lambda: ecoturismo.ejecutar(SALIDA, capas))

    estado["_generado"] = ahora()
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=1))
    fallos = [k for k, v in estado.items() if isinstance(v, dict) and v.get("ok") is False]
    print("\nMódulos con error:", fallos or "ninguno")


if __name__ == "__main__":
    main()
