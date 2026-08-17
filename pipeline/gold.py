"""
CAPA ORO — Agregados que responden las preguntas de negocio.
 
Todas las preguntas se responden SOLO con datos web (precio, descuento,
categoría), usando a Michelle Belau (competencia="PROPIA") como punto de
comparación contra el mercado (DIRECTA + INDIRECTA).
 
Tablas generadas (en SOLES, para lectura directa en la Data App):
 
  1. gold_productos.parquet
     Detalle a nivel producto de TODAS las tiendas (incluida Michelle Belau),
     con binning de precio (cuartiles) y de descuento (tramos de negocio).
     Base del explorador y los filtros.
 
  2. gold_benchmark_categoria.parquet
     Por categoría: precio de Michelle Belau vs. precio del mercado
     (promedio/min/max de la competencia).
     -> P1: ¿cómo se posiciona MB frente a la competencia por categoría?
     -> P2: ¿en qué categorías MB está por encima/debajo del promedio?
 
  3. gold_posicionamiento_producto.parquet
     Cada producto de Michelle Belau ubicado en el rango de precios del mercado
     de su categoría (posición 0..1, % vs promedio, y si está fuera de rango).
     -> P3: ¿qué productos de MB están fuera del rango típico del mercado?
 
  4. gold_descuentos_tienda.parquet
     % del catálogo en descuento y descuento promedio por tienda, con MB
     marcada, para comparar su intensidad promocional con la del mercado.
     -> P4: ¿MB descuenta más o menos que la competencia?
 
  5. gold_dispersion_categoria.parquet
     Dispersión de precios del mercado por categoría (margen de maniobra).
     -> P5: ¿qué categorías tienen más dispersión / oportunidad?
 
Reglas de binning (documentadas):
  - rango_precio: cuartiles automáticos (Económico/Medio/Premium/Lujo).
  - rango_descuento: tramos fijos (Sin descuento/Moderado/Agresivo/Liquidación).
 
Correr: python -m pipeline.gold
"""
 
import os
from datetime import date
 
import numpy as np
import pandas as pd
 
from config.settings import SILVER_DIR, GOLD_DIR, TIENDA_PROPIA
from core.transform import centimos_a_soles
from core.logger import get_logger
 
log = get_logger("gold")
 
ETIQUETAS_PRECIO = ["Económico", "Medio", "Premium", "Lujo"]
TRAMOS_DESCUENTO = [-0.1, 0, 20, 40, 100]
ETIQUETAS_DESCUENTO = ["Sin descuento", "Moderado", "Agresivo", "Liquidación"]
 
 
def _leer_silver_del_dia(fecha: str) -> pd.DataFrame:
    ruta = os.path.join(SILVER_DIR, f"silver_{fecha}.parquet")
    return pd.read_parquet(ruta) if os.path.exists(ruta) else pd.DataFrame()
 
 
def _tabla_productos(df: pd.DataFrame) -> pd.DataFrame:
    """Detalle por producto (todas las tiendas), en soles, con binning."""
    g = df.copy()
    g["precio_venta"] = g["precio_venta_centimos"].apply(centimos_a_soles)
    g["precio_etiqueta"] = g["precio_etiqueta_centimos"].apply(centimos_a_soles)
    g["monto_ahorro"] = g["monto_ahorro_centimos"].apply(centimos_a_soles)
    try:
        g["rango_precio"] = pd.qcut(g["precio_venta"], q=4,
                                     labels=ETIQUETAS_PRECIO, duplicates="drop")
    except ValueError:
        g["rango_precio"] = pd.NA
    g["rango_descuento"] = pd.cut(g["descuento_pct"], bins=TRAMOS_DESCUENTO,
                                   labels=ETIQUETAS_DESCUENTO, include_lowest=True)
    cols = ["tienda", "competencia", "id_producto", "titulo",
            "categoria_norm", "categoria_cruda",
            "precio_venta", "precio_etiqueta", "descuento_pct",
            "tiene_descuento", "monto_ahorro",
            "rango_precio", "rango_descuento", "fecha_captura"]
    return g[cols]
 
 
def _separar(df):
    """Divide en (propia, mercado) usando la etiqueta de competencia."""
    df = df.copy()
    df["precio_venta"] = df["precio_venta_centimos"] / 100
    propia = df[df["competencia"] == "PROPIA"]
    mercado = df[df["competencia"] != "PROPIA"]
    return propia, mercado
 
 
def _benchmark_categoria(propia, mercado) -> pd.DataFrame:
    """P1/P2: precio de MB vs. mercado, por categoría."""
    merc = mercado.groupby("categoria_norm", observed=True).agg(
        mercado_promedio=("precio_venta", "mean"),
        mercado_mediano=("precio_venta", "median"),
        mercado_min=("precio_venta", "min"),
        mercado_max=("precio_venta", "max"),
        mercado_n=("precio_venta", "count"),
    ).reset_index()
    mb = propia.groupby("categoria_norm", observed=True).agg(
        mb_precio_promedio=("precio_venta", "mean"),
        mb_n=("precio_venta", "count"),
    ).reset_index()
    r = merc.merge(mb, on="categoria_norm", how="left")
    r["mb_vs_mercado_pct"] = (
        (r["mb_precio_promedio"] - r["mercado_promedio"]) / r["mercado_promedio"] * 100
    ).round(1)
    for c in ["mercado_promedio", "mercado_mediano", "mercado_min", "mercado_max",
              "mb_precio_promedio"]:
        r[c] = r[c].round(2)
    return r
 
 
def _posicionamiento_producto(propia, mercado) -> pd.DataFrame:
    """P3: cada producto de MB ubicado en el rango de mercado de su categoría."""
    stats = mercado.groupby("categoria_norm", observed=True)["precio_venta"].agg(
        ["mean", "min", "max", "std"]).reset_index()
    stats.columns = ["categoria_norm", "m_prom", "m_min", "m_max", "m_std"]
    p = propia.merge(stats, on="categoria_norm", how="left")
    rango = (p["m_max"] - p["m_min"]).replace(0, np.nan)
    p["posicion_en_mercado"] = ((p["precio_venta"] - p["m_min"]) / rango).clip(0, 1).round(2)
    p["vs_promedio_pct"] = ((p["precio_venta"] - p["m_prom"]) / p["m_prom"] * 100).round(1)
    # fuera de rango: a más de 2 desviaciones del promedio del mercado
    p["z"] = (p["precio_venta"] - p["m_prom"]) / p["m_std"].replace(0, np.nan)
    p["fuera_de_rango"] = p["z"].abs() > 2
    p["señal"] = np.select(
        [p["z"] > 2, p["z"] < -2],
        ["Caro vs. mercado", "Barato vs. mercado"],
        default="En rango",
    )
    return p[["id_producto", "titulo", "categoria_norm", "precio_venta",
              "m_prom", "m_min", "m_max", "posicion_en_mercado", "vs_promedio_pct",
              "fuera_de_rango", "señal"]].rename(columns={
                  "m_prom": "mercado_promedio", "m_min": "mercado_min", "m_max": "mercado_max"})
 
 
def _descuentos_tienda(df) -> pd.DataFrame:
    """P4: intensidad de descuento por tienda (MB marcada para comparar)."""
    r = df.groupby(["tienda", "competencia"], observed=True).agg(
        n_productos=("id_producto", "count"),
        pct_en_descuento=("tiene_descuento", "mean"),
        descuento_promedio=("descuento_pct", "mean"),
    ).reset_index()
    r["pct_en_descuento"] = (r["pct_en_descuento"] * 100).round(1)
    r["descuento_promedio"] = r["descuento_promedio"].round(1)
    r["es_propia"] = r["competencia"] == "PROPIA"
    return r
 
 
def _dispersion_categoria(mercado) -> pd.DataFrame:
    """P5: dispersión de precios del mercado por categoría (oportunidad)."""
    r = mercado.groupby("categoria_norm", observed=True).agg(
        precio_promedio=("precio_venta", "mean"),
        dispersion=("precio_venta", "std"),
        precio_min=("precio_venta", "min"),
        precio_max=("precio_venta", "max"),
        n_productos=("precio_venta", "count"),
        pct_en_descuento=("tiene_descuento", "mean"),
    ).reset_index()
    r["rango_precio_amplitud"] = (r["precio_max"] - r["precio_min"]).round(2)
    r["pct_en_descuento"] = (r["pct_en_descuento"] * 100).round(1)
    for c in ["precio_promedio", "dispersion", "precio_min", "precio_max"]:
        r[c] = r[c].round(2)
    return r
 
 
def _actualizar_historico(propia, mercado, fecha):
    """
    Acumula un histórico de precio promedio por categoría y fecha, con DOS
    series: Michelle Belau y mercado.
 
    Guarda DOS niveles:
      - Por categoria_norm: promedio de esa categoría (para ver evolución por cat.)
      - "TODAS": promedio ponderado real de TODOS los productos (no promedio de
        promedios), para que coincida con los KPIs de la app.
 
    Upsert por fecha: si ya existe una fila para esa fecha, se reemplaza.
    La fecha se guarda siempre como string YYYY-MM-DD para evitar mezcla de tipos.
    """
    ruta = os.path.join(GOLD_DIR, "gold_historico_precios.parquet")
    fecha_str = str(fecha)[:10]  # garantizar YYYY-MM-DD sin hora
 
    partes = []
    for df_serie, nombre in [(mercado, "Mercado"), (propia, "Michelle Belau")]:
        if df_serie.empty:
            continue
        # por categoría
        por_cat = (df_serie.groupby("categoria_norm", observed=True)["precio_venta"]
                   .mean().reset_index())
        por_cat["serie"] = nombre
        por_cat.rename(columns={"precio_venta": "precio_promedio"}, inplace=True)
        # global ponderado (promedio de todos los productos, no de categorías)
        global_row = pd.DataFrame([{
            "categoria_norm": "TODAS",
            "serie": nombre,
            "precio_promedio": round(float(df_serie["precio_venta"].mean()), 2),
        }])
        partes.extend([por_cat, global_row])
 
    if not partes:
        return
 
    hoy = pd.concat(partes, ignore_index=True)
    hoy["fecha"] = fecha_str
    hoy["precio_promedio"] = hoy["precio_promedio"].round(2)
    hoy = hoy[["fecha", "categoria_norm", "serie", "precio_promedio"]]
 
    if os.path.exists(ruta):
        previo = pd.read_parquet(ruta)
        # normalizar fecha del previo también a string puro
        previo["fecha"] = previo["fecha"].astype(str).str[:10]
        previo = previo[previo["fecha"] != fecha_str]
        hoy = pd.concat([previo, hoy], ignore_index=True)
 
    hoy.to_parquet(ruta, index=False)
    log.info(f"Histórico de precios actualizado ({hoy['fecha'].nunique()} fechas)")


def ejecutar(fecha: str | None = None) -> bool:
    fecha = fecha or date.today().isoformat()
    log.info(f"=== GOLD: agregando silver del {fecha} ===")

    df = _leer_silver_del_dia(fecha)
    if df.empty:
        log.warning("No hay datos de silver. ¿Corriste bronce + silver?")
        return False

    _tabla_productos(df).to_parquet(
        os.path.join(GOLD_DIR, "gold_productos.parquet"), index=False)

    propia, mercado = _separar(df)
    if propia.empty:
        log.warning("No hay productos de Michelle Belau (PROPIA) en los datos. "
                    "El benchmark y posicionamiento quedarán vacíos.")

    _descuentos_tienda(df).to_parquet(
        os.path.join(GOLD_DIR, "gold_descuentos_tienda.parquet"), index=False)
    _dispersion_categoria(mercado).to_parquet(
        os.path.join(GOLD_DIR, "gold_dispersion_categoria.parquet"), index=False)

    if not propia.empty and not mercado.empty:
        _benchmark_categoria(propia, mercado).to_parquet(
            os.path.join(GOLD_DIR, "gold_benchmark_categoria.parquet"), index=False)
        _posicionamiento_producto(propia, mercado).to_parquet(
            os.path.join(GOLD_DIR, "gold_posicionamiento_producto.parquet"), index=False)
 
    # histórico acumulado (habilita la evolución temporal en la app)
    _actualizar_historico(propia, mercado, fecha)
 
    log.info(f"=== GOLD guardada ({len(df)} productos, "
             f"MB: {len(propia)}, mercado: {len(mercado)}) ===")
    return True
 
 
if __name__ == "__main__":
    ejecutar()
