"""
CAPA BRONCE — Ingesta bruta.

Descarga el catálogo de cada tienda Shopify TAL CUAL viene de la API (sin
transformar) y lo guarda en DOS formatos optimizados:
  - Avro    (.avro)     -> formato de fila, ideal para el JSON crudo anidado;
                           esquema autodescriptivo, óptimo para archivar ingesta.
  - Parquet (.parquet)  -> formato columnar, para releer rápido en la capa silver.

Guardar ambos da lo mejor de dos mundos: Avro preserva fielmente el crudo de
ingesta (row-based, como llega de la API) y Parquet permite lectura columnar
eficiente aguas abajo. De cualquiera se puede reconstruir todo sin re-descargar.

Cada archivo tiene una fila por página de respuesta, con el JSON crudo como
texto + metadatos.

Manejo de errores: cada tienda se ingiere aislada; si una falla, se registra en
el manifiesto y las demás continúan. Reintentos automáticos con backoff.

Correr: python -m pipeline.bronze
"""

import json
import os
from datetime import date, datetime

import pandas as pd
import fastavro

from config.tiendas import TIENDAS_SHOPIFY
from config.settings import BRONZE_DIR
from core.http_client import crear_sesion, get_json
from core.logger import get_logger
from core.manifiesto import registrar_corrida, Cronometro

log = get_logger("bronze")

LIMIT = 250  # máximo por página en Shopify

# Esquema Avro: metadatos fijos + el JSON crudo como string (el JSON de cada
# plataforma tiene forma distinta, así que no se tipa campo por campo).
AVRO_SCHEMA = {
    "type": "record",
    "name": "PaginaCruda",
    "fields": [
        {"name": "tienda", "type": "string"},
        {"name": "competencia", "type": "string"},
        {"name": "plataforma", "type": "string"},
        {"name": "fecha_captura", "type": "string"},
        {"name": "timestamp", "type": "string"},
        {"name": "pagina", "type": "int"},
        {"name": "url", "type": "string"},
        {"name": "json_crudo", "type": "string"},
        {"name": "n_productos", "type": "int"},
    ],
}


def _ingerir_tienda(tienda: dict, sesion) -> int:
    """Descarga todas las páginas de una tienda y las guarda en Avro + Parquet."""
    nombre = tienda["nombre"]
    base_url = tienda["base_url"]
    fecha = date.today().isoformat()
    ahora = datetime.now().isoformat(timespec="seconds")

    registros = []
    pagina = 1
    while True:
        params = {"limit": LIMIT, "page": pagina}
        data = get_json(sesion, base_url, params=params, logger=log)
        if data is None:
            log.error(f"[{nombre}] fallo al pedir página {pagina}")
            break
        productos = data.get("products", [])
        log.info(f"[{nombre}] página {pagina}: {len(productos)} productos")

        registros.append({
            "tienda": nombre,
            "competencia": tienda["competencia"],
            "plataforma": tienda["plataforma"],
            "fecha_captura": fecha,
            "timestamp": ahora,
            "pagina": pagina,
            "url": f"{base_url}?limit={LIMIT}&page={pagina}",
            "json_crudo": json.dumps(data, ensure_ascii=False),
            "n_productos": len(productos),
        })

        if len(productos) == 0:
            break
        pagina += 1

    carpeta = os.path.join(BRONZE_DIR, nombre)
    os.makedirs(carpeta, exist_ok=True)

    # 1. Avro (row-based, crudo de ingesta)
    ruta_avro = os.path.join(carpeta, f"bronze_{nombre}_{fecha}.avro")
    with open(ruta_avro, "wb") as f:
        fastavro.writer(f, AVRO_SCHEMA, registros)

    # 2. Parquet (columnar, para releer en silver)
    ruta_parquet = os.path.join(carpeta, f"bronze_{nombre}_{fecha}.parquet")
    pd.DataFrame(registros).to_parquet(ruta_parquet, index=False)

    log.info(f"[{nombre}] guardado bronce: Avro + Parquet ({len(registros)} páginas)")
    return len(registros)


def ejecutar() -> bool:
    """Ingesta de todas las tiendas. True si todas OK; False si alguna falló."""
    log.info(f"=== BRONCE: ingesta de {len(TIENDAS_SHOPIFY)} tiendas ===")
    sesion = crear_sesion()
    todas_ok = True

    for tienda in TIENDAS_SHOPIFY:
        nombre = tienda["nombre"]
        estado, error, paginas = "ok", None, 0
        with Cronometro() as cron:
            try:
                paginas = _ingerir_tienda(tienda, sesion)
            except Exception as e:
                log.error(f"[{nombre}] error de ingesta: {e}", exc_info=True)
                estado, error, todas_ok = "error", str(e), False
        registrar_corrida(
            capa="bronze", tienda=nombre, competencia=tienda["competencia"],
            plataforma=tienda["plataforma"], filas=paginas,
            duracion_seg=getattr(cron, "duracion", 0), estado=estado, mensaje_error=error,
        )

    log.info("=== BRONCE terminada " + ("(todas OK)" if todas_ok else "(con errores)") + " ===")
    return todas_ok


if __name__ == "__main__":
    ejecutar()
