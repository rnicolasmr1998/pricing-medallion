"""
CAPA SILVER — Limpieza, transformación, validación y reglas de negocio.

Lee el Parquet crudo de bronce, aplana el JSON de Shopify a una fila por producto
y produce un dataset limpio, tipado y validado, guardado en Parquet.

Transformaciones documentadas (en orden):
  1. Aplanado: de JSON anidado (producto -> variants) a una fila por PRODUCTO.
     Se toma la 1ª variante: el precio no cambia por talla, así no se duplica.
  2. Parseo de precios a céntimos (entero) -> exactitud en cálculos.
  2b. Conversión USD -> soles para tiendas en dólares (config: TIENDAS_EN_USD,
      TIPO_CAMBIO_USD=3.50). Actualmente: amalfitana.
  3. Manejo de faltantes:
       - sin precio de venta -> se descarta.
       - sin precio de etiqueta -> se asume = precio de venta (sin descuento).
       - sin categoría cruda -> "NO INDICA".
  4. Reglas de negocio derivadas:
       - descuento_pct = (etiqueta - venta) / etiqueta  (0 si no aplica)
       - tiene_descuento = descuento_pct > 0
       - monto_ahorro_centimos = etiqueta - venta (>= 0)
  5. Normalización de categorías -> taxonomía propia (categoria_norm).
     Fallback para Ecru: si no hay product_type, deduce de la 2ª palabra del título.
  5b. Descarte de productos con categoría no resuelta (SIN_MAPEAR / SIN_CATEGORIA).
      No aportan al análisis de pricing y contaminarían el benchmark.
  6. Optimización de memoria: downcast de enteros, category en baja cardinalidad.
  7. Validación con pandera: contrato de tipos y rangos.

Correr: python -m pipeline.silver
"""

import glob
import json
import os
from datetime import date

import pandas as pd
import pandera.pandas as pa
from pandera.pandas import Column, DataFrameSchema, Check

from config.settings import (BRONZE_DIR, SILVER_DIR, CATEGORIAS_MAP_PATH,
                              SIN_MAPEAR_PATH, TIPO_CAMBIO_USD, TIENDAS_EN_USD)
from core.transform import parsear_precio_centimos, calcular_descuento, FORMATO_PERUANO
from core.normalize import cargar_mapa, normalizar, guardar_no_mapeados
from core.logger import get_logger

log = get_logger("silver")


# --- Esquema de validación (contrato de la capa silver) --------------------
ESQUEMA_SILVER = DataFrameSchema(
    {
        "tienda": Column(str),
        "competencia": Column(str, Check.isin(["DIRECTA", "INDIRECTA", "PROPIA"])),
        "id_producto": Column(str),
        "titulo": Column(str, nullable=True),
        "vendedor": Column(str, nullable=True),
        "categoria_cruda": Column(str),
        "categoria_norm": Column(str),
        "precio_venta_centimos": Column(int, Check.gt(0)),
        "precio_etiqueta_centimos": Column(int, Check.gt(0)),
        "descuento_pct": Column(int, Check.in_range(0, 100)),
        "tiene_descuento": Column(bool),
        "monto_ahorro_centimos": Column(int, Check.ge(0)),
        "fecha_captura": Column(str),
    },
    strict=False,
    coerce=True,
)


def _leer_bronce_del_dia(fecha: str) -> pd.DataFrame:
    """Lee y concatena todos los Parquet de bronce de una fecha."""
    patron = os.path.join(BRONZE_DIR, "*", f"bronze_*_{fecha}.parquet")
    trozos = [pd.read_parquet(r) for r in glob.glob(patron)]
    return pd.concat(trozos, ignore_index=True) if trozos else pd.DataFrame()


def _separar_categoria(product_type):
    """
    Separa 'Categoría > Subcategoría' en (categoria, subcategoria).

    Algunas tiendas (ej. Michelle Belau) traen la categoría anidada en un solo
    campo con '>': "Abrigos > Abrigos Manga Larga". Se toma lo de ANTES del '>'
    como categoría (mapeable) y lo de después como subcategoría.

        "Abrigos > Abrigos Manga Larga" -> ("Abrigos", "Abrigos Manga Larga")
        "Pantalones > Pantalones Rectos" -> ("Pantalones", "Pantalones Rectos")
        "Vestido"                        -> ("Vestido", None)
        None / ""                        -> ("NO INDICA", None)
    """
    if not product_type or not str(product_type).strip():
        return "NO INDICA", None
    partes = str(product_type).split(">", 1)
    categoria = partes[0].strip()
    subcategoria = partes[1].strip() if len(partes) > 1 and partes[1].strip() else None
    return (categoria or "NO INDICA"), subcategoria


# --- Regla específica de ECRU ----------------------------------------------
# Ecru no trae product_type: sus productos caen en SIN_CATEGORIA. Pero el
# título codifica el tipo de prenda en inglés como SEGUNDA palabra:
#   "WINDSOR BAG"           -> BAG    -> Accesorios
#   "TEASEL BLOUSE CARAMEL" -> BLOUSE -> Tops
# Este diccionario traduce esa palabra inglesa a la categoría normalizada.
# Se usa SOLO para Ecru, como fallback antes de dar SIN_CATEGORIA.
ECRU_PALABRA_CATEGORIA = {
    # Blusas
    "BLOUSE": "Blusas", "SHIRT": "Blusas", "TOP": "Blusas", "TEE": "Blusas",
    "TSHIRT": "Blusas", "T-SHIRT": "Blusas", "POLO": "Blusas",
    "CAMISOLE": "Blusas", "BODYSUIT": "Blusas", "BODY": "Blusas",
    "HALTER": "Blusas", "TANK": "Blusas",
    # Vestidos & Enterizos
    "DRESS": "Vestidos & Enterizos", "JUMPSUIT": "Vestidos & Enterizos",
    "ROMPER": "Vestidos & Enterizos", "OVERALL": "Vestidos & Enterizos",
    "KAFTAN": "Vestidos & Enterizos",
    # Pantalones
    "PANTS": "Pantalones", "PANT": "Pantalones", "TROUSERS": "Pantalones",
    "JEAN": "Pantalones", "JEANS": "Pantalones",
    "LEGGINGS": "Pantalones", "CAPRI": "Pantalones",
    "CULOTTE": "Pantalones", "CULOTTES": "Pantalones",
    # Faldas
    "SKIRT": "Faldas",
    # Shorts
    "SHORT": "Shorts", "SHORTS": "Shorts",
    # Abrigos
    "COAT": "Abrigos", "TRENCH": "Abrigos",
    "CAPE": "Abrigos", "PONCHO": "Abrigos", "PARKA": "Abrigos",
    # Sacos & Blazers
    "BLAZER": "Sacos & Blazers", "VEST": "Sacos & Blazers",
    # Casacas
    "JACKET": "Casacas",
    # Chalecos
    "GILET": "Chalecos",
    # Chompas & Cardigans
    "SWEATER": "Chompas & Cardigans", "CARDIGAN": "Chompas & Cardigans",
    "KNIT": "Chompas & Cardigans", "PULLOVER": "Chompas & Cardigans",
    "HOODIE": "Chompas & Cardigans", "SWEATSHIRT": "Chompas & Cardigans",
    # Carteras
    "BAG": "Carteras", "CLUTCH": "Carteras", "TOTE": "Carteras",
    "WALLET": "Carteras",
    # EXCLUIR: calzado y accesorios varios
    "SHOES": "EXCLUIR", "SHOE": "EXCLUIR", "BOOT": "EXCLUIR",
    "BOOTS": "EXCLUIR", "SANDAL": "EXCLUIR", "SANDALS": "EXCLUIR",
    "HEEL": "EXCLUIR", "HEELS": "EXCLUIR", "FLAT": "EXCLUIR",
    "FLATS": "EXCLUIR", "SNEAKER": "EXCLUIR", "SNEAKERS": "EXCLUIR",
    "BELT": "EXCLUIR", "SCARF": "EXCLUIR", "HAT": "EXCLUIR",
    "NECKLACE": "EXCLUIR", "EARRINGS": "EXCLUIR", "BRACELET": "EXCLUIR",
    "RING": "EXCLUIR", "GLOVES": "EXCLUIR",
}


def categoria_ecru_desde_titulo(titulo):
    """
    Fallback para Ecru: devuelve la categoría normalizada según la SEGUNDA
    palabra del título (en inglés), o None si no se reconoce.
        "WINDSOR BAG" -> "Accesorios"
        "TEASEL BLOUSE CARAMEL" -> "Tops"
    """
    if not titulo:
        return None
    palabras = str(titulo).strip().upper().split()
    if len(palabras) < 2:
        return None
    return ECRU_PALABRA_CATEGORIA.get(palabras[1])


def _aplanar(bronce: pd.DataFrame) -> pd.DataFrame:
    """Aplana el JSON crudo de cada página a filas por producto."""
    filas = []
    for _, reg in bronce.iterrows():
        data = json.loads(reg["json_crudo"])
        for prod in data.get("products", []):
            variantes = prod.get("variants", [])
            if not variantes:
                continue
            v = variantes[0]  # el precio es igual en todas las tallas
            handle = prod.get("handle")
            categoria_cruda, subcategoria_cruda = _separar_categoria(prod.get("product_type"))
            filas.append({
                "tienda": reg["tienda"],
                "competencia": reg["competencia"],
                "fecha_captura": reg["fecha_captura"],
                "id_producto": str(prod.get("id")),
                "titulo": prod.get("title"),
                "vendedor": prod.get("vendor"),
                "categoria_cruda": categoria_cruda,
                "subcategoria_cruda": subcategoria_cruda,
                "precio_venta_raw": v.get("price"),
                "precio_etiqueta_raw": v.get("compare_at_price"),
                "handle": handle,
            })
    return pd.DataFrame(filas)


def _transformar(df: pd.DataFrame) -> tuple[pd.DataFrame, set]:
    """Parseo de precios, faltantes, reglas de negocio, normalización de categoría."""
    # 2. precios a céntimos
    df["precio_venta_centimos"] = df["precio_venta_raw"].apply(
        lambda x: parsear_precio_centimos(x, FORMATO_PERUANO))
    df["precio_etiqueta_centimos"] = df["precio_etiqueta_raw"].apply(
        lambda x: parsear_precio_centimos(x, FORMATO_PERUANO))

    # 2b. conversión USD -> soles para tiendas con precios en dólares
    mask_usd = df["tienda"].isin(TIENDAS_EN_USD)
    if mask_usd.any():
        def _usd_a_soles(x):
            try:
                if x is None or pd.isna(x):
                    return x
                return int(x * TIPO_CAMBIO_USD)
            except (TypeError, ValueError):
                return x
        df.loc[mask_usd, "precio_venta_centimos"] = (
            df.loc[mask_usd, "precio_venta_centimos"].apply(_usd_a_soles))
        df.loc[mask_usd, "precio_etiqueta_centimos"] = (
            df.loc[mask_usd, "precio_etiqueta_centimos"].apply(_usd_a_soles))
        log.info(f"Precios de {TIENDAS_EN_USD} convertidos USD→S/. (TC={TIPO_CAMBIO_USD})")

    # 3. faltantes
    antes = len(df)
    df = df[df["precio_venta_centimos"].notna() & (df["precio_venta_centimos"] > 0)].copy()
    descartados = antes - len(df)
    if descartados:
        log.warning(f"Descartados {descartados} productos sin precio de venta válido")
    df["precio_etiqueta_centimos"] = df["precio_etiqueta_centimos"].fillna(
        df["precio_venta_centimos"])
    # asegurar etiqueta >= venta (si viene menor, no hay descuento real)
    df.loc[df["precio_etiqueta_centimos"] < df["precio_venta_centimos"],
           "precio_etiqueta_centimos"] = df["precio_venta_centimos"]

    df["precio_venta_centimos"] = df["precio_venta_centimos"].astype(int)
    df["precio_etiqueta_centimos"] = df["precio_etiqueta_centimos"].astype(int)

    # 4. reglas de negocio (vectorizado)
    df["descuento_pct"] = [
        calcular_descuento(v, e)
        for v, e in zip(df["precio_venta_centimos"], df["precio_etiqueta_centimos"])
    ]
    df["tiene_descuento"] = df["descuento_pct"] > 0
    df["monto_ahorro_centimos"] = (
        df["precio_etiqueta_centimos"] - df["precio_venta_centimos"]).clip(lower=0)

    # 5. normalización de categorías
    mapa = cargar_mapa(CATEGORIAS_MAP_PATH)
    no_mapeados = set()

    def _norm_fila(tienda, cat, subcat, titulo):
        resultado = normalizar(tienda, cat, subcat, mapa, no_mapeados=None)
        # Fallback SOLO para Ecru: si no se pudo mapear (o cae en categoría no
        # útil), intentar deducir la categoría de la 2ª palabra del título.
        if tienda == "ecru" and resultado in ("SIN_MAPEAR", "SIN_CATEGORIA", "EXCLUIR"):
            desde_titulo = categoria_ecru_desde_titulo(titulo)
            if desde_titulo and desde_titulo != "EXCLUIR":
                return desde_titulo
        # registrar como no mapeada solo si finalmente no se resolvió
        if resultado == "SIN_MAPEAR":
            no_mapeados.add((tienda, cat or "", subcat if isinstance(subcat, str) else ""))
        return resultado

    df["categoria_norm"] = [
        _norm_fila(t, c, s, tit)
        for t, c, s, tit in zip(df["tienda"], df["categoria_cruda"],
                                df["subcategoria_cruda"], df["titulo"])
    ]

    # 5b. DESCARTAR productos cuya categoría no pudo resolverse o está marcada
    #     como EXCLUIR (calzado, accesorios, gift cards, etc. — no relevantes
    #     para el análisis de pricing de ropa).
    antes = len(df)
    df = df[~df["categoria_norm"].isin(["SIN_MAPEAR", "SIN_CATEGORIA", "EXCLUIR"])].copy()
    descartados_cat = antes - len(df)
    if descartados_cat:
        log.warning(f"Descartados {descartados_cat} productos (categoría no resuelta o excluida)")

    return df, no_mapeados


def _optimizar_memoria(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.select_dtypes(include=["int64", "int"]).columns:
        df[col] = pd.to_numeric(df[col], downcast="integer")
    for col in ["tienda", "competencia", "categoria_norm", "categoria_cruda", "vendedor"]:
        if col in df.columns:
            df[col] = df[col].astype("category")
    return df


def ejecutar(fecha: str | None = None) -> bool:
    fecha = fecha or date.today().isoformat()
    log.info(f"=== SILVER: procesando bronce del {fecha} ===")

    bronce = _leer_bronce_del_dia(fecha)
    if bronce.empty:
        log.warning("No hay datos de bronce para hoy. ¿Corriste la capa bronce?")
        return False

    df = _aplanar(bronce)
    log.info(f"Aplanado: {len(df)} productos")

    df, no_mapeados = _transformar(df)
    if no_mapeados:
        guardar_no_mapeados(no_mapeados, SIN_MAPEAR_PATH)
        log.warning(f"{len(no_mapeados)} categorías sin mapear -> {SIN_MAPEAR_PATH}")

    # columnas finales (se descartan las _raw y auxiliares)
    cols = ["tienda", "competencia", "id_producto", "titulo", "vendedor",
            "categoria_cruda", "categoria_norm",
            "precio_venta_centimos", "precio_etiqueta_centimos",
            "descuento_pct", "tiene_descuento", "monto_ahorro_centimos",
            "fecha_captura"]
    df = df[cols]

    # 7. validación
    df = ESQUEMA_SILVER.validate(df)
    # 6. optimización de memoria
    df = _optimizar_memoria(df)

    ruta = os.path.join(SILVER_DIR, f"silver_{fecha}.parquet")
    df.to_parquet(ruta, index=False)
    log.info(f"=== SILVER guardada: {ruta} ({len(df)} filas) ===")
    return True


if __name__ == "__main__":
    ejecutar()
