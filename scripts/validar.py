"""Control de calidad antes de publicar. Falla (código 1) si las salidas que lee la página están rotas
o si el módulo de fuego lleva demasiado tiempo sin un dato bueno; GitHub avisa por correo al dueño.

    python scripts/validar.py              # estructura de las salidas (antes de publicar)
    python scripts/validar.py --frescura   # además, antigüedad del dato de fuego (después de publicar)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "docs" / "data"
MAX_HORAS_FUEGO = 3

errores: list[str] = []


def cargar(nombre: str):
    f = DATA / nombre
    if not f.exists():
        errores.append(f"falta {nombre}")
        return None
    try:
        return json.loads(f.read_text())
    except json.JSONDecodeError as e:
        errores.append(f"{nombre} no es JSON válido: {e}")
        return None


focos = cargar("focos.geojson")
if focos is not None and (focos.get("type") != "FeatureCollection" or not isinstance(focos.get("features"), list)):
    errores.append("focos.geojson no es una FeatureCollection")

resumen = cargar("resumen.json")
if resumen is not None and "totales" not in resumen:
    errores.append("resumen.json sin totales")

estado = cargar("estado.json")
if estado is not None and "--frescura" in sys.argv:
    f = estado.get("fuego", {})
    ref = f.get("actualizado")
    if not ref:
        errores.append("el módulo de fuego nunca terminó bien")
    else:
        horas = (datetime.now(timezone.utc) - datetime.fromisoformat(ref)).total_seconds() / 3600
        if horas > MAX_HORAS_FUEGO:
            errores.append(f"fuego sin dato bueno hace {horas:.1f} h (último error: {f.get('error')})")

serie = cargar("serie_focos.json")
if serie is not None and not serie.get("meses"):
    errores.append("serie_focos.json vacía")

if errores:
    print("Validación con errores:\n- " + "\n- ".join(errores))
    sys.exit(1)
print("Validación correcta.")
