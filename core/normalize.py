"""
Normalización de categorías: cruza categorías crudas de cada tienda contra la
taxonomía propia (config/categorias_map.csv). Usado en la capa SILVER.

El mapa se carga una vez; normalizar() es búsqueda pura y acumula las
combinaciones no encontradas en un set, que se vuelca al final a sin_mapear.csv.
"""

import csv
import os

import pandas as pd

VALOR_SIN_MAPEAR = "SIN_MAPEAR"


def _clave(tienda, cat, subcat):
    def limpiar(x):
        # trata None, NaN (float) y vacíos por igual
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return ""
        return str(x).strip().lower()
    return (limpiar(tienda), limpiar(cat), limpiar(subcat))


def cargar_mapa(ruta_csv) -> dict:
    mapa = {}
    with open(ruta_csv, encoding="utf-8-sig") as f:
        for fila in csv.DictReader(f):
            mapa[_clave(fila.get("tienda"), fila.get("categoria_cruda"),
                        fila.get("subcategoria_cruda"))] = (fila.get("categoria_norm") or "").strip()
    return mapa


def normalizar(tienda, categoria_cruda, subcategoria_cruda, mapa, no_mapeados=None):
    """Match específico (con subcat) -> general (sin subcat) -> SIN_MAPEAR."""
    esp = _clave(tienda, categoria_cruda, subcategoria_cruda)
    if esp in mapa:
        return mapa[esp]
    gen = _clave(tienda, categoria_cruda, "")
    if gen in mapa:
        return mapa[gen]
    if no_mapeados is not None:
        def _txt(x):
            if x is None or (isinstance(x, float) and pd.isna(x)):
                return ""
            return str(x)
        no_mapeados.add((_txt(tienda), _txt(categoria_cruda), _txt(subcategoria_cruda)))
    return VALOR_SIN_MAPEAR


def guardar_no_mapeados(no_mapeados, ruta_csv):
    if not no_mapeados:
        return None
    os.makedirs(os.path.dirname(ruta_csv), exist_ok=True)
    with open(ruta_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tienda", "categoria_cruda", "subcategoria_cruda"])
        for t, c, s in sorted(no_mapeados):
            w.writerow([t, c, s])
    return ruta_csv
