"""
Rutas y constantes centralizadas del proyecto (arquitectura medallón).
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")
BRONZE_DIR = os.path.join(DATA_DIR, "bronze")   # datos brutos (Arrow)
SILVER_DIR = os.path.join(DATA_DIR, "silver")   # limpio + validado (Parquet)
GOLD_DIR = os.path.join(DATA_DIR, "gold")       # agregados de negocio (Parquet)

LOGS_DIR = os.path.join(BASE_DIR, "logs")
MANIFIESTO_PATH = os.path.join(LOGS_DIR, "manifiesto.jsonl")
SIN_MAPEAR_PATH = os.path.join(LOGS_DIR, "sin_mapear.csv")

CONFIG_DIR = os.path.join(BASE_DIR, "config")
CATEGORIAS_MAP_PATH = os.path.join(CONFIG_DIR, "categorias_map.csv")

for _d in (BRONZE_DIR, SILVER_DIR, GOLD_DIR, LOGS_DIR):
    os.makedirs(_d, exist_ok=True)

# HTTP
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}
HTTP_TIMEOUT = 30
HTTP_REINTENTOS = 3
HTTP_BACKOFF = 2.0

TIENDA_PROPIA = "michelle_belau"   # la tienda propia, para comparar vs. mercado

# --- Tipo de cambio --------------------------------------------------------
# Tiendas cuyos precios vienen en USD y deben convertirse a soles en silver.
# Ajustar TIPO_CAMBIO_USD cuando cambie el tipo de cambio real.
TIPO_CAMBIO_USD = 3.50          # soles por dólar (variable fija; ajustar si cambia)
TIENDAS_EN_USD = {"amalfitana"} # set de tiendas con precios en dólares
