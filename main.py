"""
Orquestador del pipeline medallón: bronce -> silver -> gold.

Uso:
    python main.py                 -> corre las 3 capas en orden
    python main.py --solo bronze   -> solo ingesta
    python main.py --solo silver   -> solo limpieza/transformación
    python main.py --solo gold      -> solo agregados
    python main.py --desde silver   -> desde silver en adelante (silver + gold)

Regla de seguridad: si una capa falla, no se ejecutan las siguientes (no tiene
sentido procesar sobre datos incompletos). Las capas se pueden correr por
separado para reprocesar sin re-descargar (ej. --solo silver tras ajustar el
mapa de categorías).
"""

import argparse

from pipeline import bronze, silver, gold
from core.logger import get_logger

log = get_logger("main")

CAPAS = ["bronze", "silver", "gold"]


def main():
    parser = argparse.ArgumentParser(description="Pipeline medallón de pricing.")
    parser.add_argument("--solo", choices=CAPAS, help="Ejecuta solo esa capa.")
    parser.add_argument("--desde", choices=CAPAS, help="Ejecuta desde esa capa en adelante.")
    args = parser.parse_args()

    if args.solo:
        a_correr = [args.solo]
    elif args.desde:
        a_correr = CAPAS[CAPAS.index(args.desde):]
    else:
        a_correr = CAPAS

    log.info(f"=== INICIO | capas: {', '.join(a_correr)} ===")

    funciones = {"bronze": bronze.ejecutar, "silver": silver.ejecutar, "gold": gold.ejecutar}
    for capa in a_correr:
        ok = funciones[capa]()
        if not ok:
            log.error(f"La capa '{capa}' no completó. Se detiene el pipeline "
                      f"para no procesar sobre datos incompletos.")
            break

    log.info("=== FIN ===")


if __name__ == "__main__":
    main()
