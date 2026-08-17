"""
Data App — Inteligencia de precios: Michelle Belau vs. la competencia.

Lee las tablas de data/gold/ y las presenta con filtros y gráficos interactivos.
Un botón ejecuta todo el ETL (bronce -> silver -> gold) en vivo.

Todas las preguntas se responden con la información disponible de las páginas web, 
usando a Michelle Belau como punto de comparación contra el mercado 
(competencia DIRECTA + INDIRECTA).

Correr:  streamlit run app/app.py
"""


import os
import sys
import subprocess

import requests
import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import GOLD_DIR, BASE_DIR

st.set_page_config(page_title="Pricing — Michelle Belau vs. Mercado", layout="wide")
PALETA = px.colors.qualitative.Set2
COLOR_MB = "#d6336c"
COLOR_MERCADO = "#adb5bd"


@st.cache_data
def cargar(nombre):
    ruta = os.path.join(GOLD_DIR, nombre)
    return pd.read_parquet(ruta) if os.path.exists(ruta) else pd.DataFrame()


def correr_etl_cloud():
    """
    Dispara el workflow de GitHub Actions vía API.
    Requiere GITHUB_TOKEN y GITHUB_REPO en los Secrets de Streamlit Cloud.
    Devuelve el objeto Response (204 = OK) o None si faltan las variables.
    """
    token = os.getenv("GITHUB_TOKEN", "")
    repo  = os.getenv("GITHUB_REPO", "")
    if not token or not repo:
        return None
    url = (f"https://api.github.com/repos/{repo}/actions/workflows/"
           f"pipeline.yml/dispatches")
    return requests.post(
        url,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
        json={"ref": "main"},
        timeout=10,
    )


def correr_etl_local():
    """Fallback para entorno local: corre main.py como subproceso."""
    return subprocess.run(
        [sys.executable, "main.py"],
        cwd=BASE_DIR, capture_output=True, text=True)


def eje_soles(fig, titulo_y="Precio (S/.)"):
    fig.update_yaxes(title_text=titulo_y, tickprefix="S/. ")
    return fig


# Encabezado + botón actualizar
c_tit, c_btn = st.columns([4, 1])
with c_tit:
    st.title("Pricing Intelligence — Michelle Belau vs. Mercado")
with c_btn:
    st.write("")
    if st.button(label="Actualizar datos", width='stretch',
                 help="En nube: dispara GitHub Actions. En local: corre el pipeline directamente."):

        es_cloud = bool(os.getenv("GITHUB_TOKEN") and os.getenv("GITHUB_REPO"))

        if es_cloud:
            # --- Modo nube: disparar GitHub Actions ---
            with st.spinner("Iniciando pipeline en GitHub Actions…"):
                res = correr_etl_cloud()
            if res is None:
                st.error("GITHUB_TOKEN o GITHUB_REPO no configurados en Secrets.")
            elif res.status_code == 204:
                st.success(
                    "✅ Pipeline iniciado. Los datos estarán listos en ~3 minutos. "
                    "Recarga la página para ver los cambios.")
            else:
                st.error(f"Error al disparar el workflow: HTTP {res.status_code}")
                st.code(res.text[:800])
        else:
            # --- Modo local: subproceso directo ---
            with st.spinner("Ejecutando ETL local: descargando tiendas…"):
                res_local = correr_etl_local()
            if res_local.returncode == 0:
                st.cache_data.clear()
                st.success("✅ Datos actualizados.")
                st.rerun()
            else:
                st.error("El ETL falló. Revisa logs/errores.log")
                st.code((res_local.stderr or res_local.stdout)[-1500:])

productos = cargar("gold_productos.parquet")
benchmark = cargar("gold_benchmark_categoria.parquet")
posicion  = cargar("gold_posicionamiento_producto.parquet")
descuentos = cargar("gold_descuentos_tienda.parquet")
dispersion = cargar("gold_dispersion_categoria.parquet")
historico  = cargar("gold_historico_precios.parquet")

if productos.empty:
    st.warning("No hay datos en la capa gold. Pulsa **Actualizar datos** "
               "o corre `python main.py`.")
    st.stop()

hay_mb = (productos["competencia"] == "PROPIA").any()
fecha_datos = productos["fecha_captura"].iloc[0] if "fecha_captura" in productos else "—"
st.caption(f"Datos al {fecha_datos} · {len(productos):,} productos · "
           f"{productos['tienda'].nunique()} tiendas"
           + ("" if hay_mb else " · ⚠️ Michelle Belau no aparece en los datos"))

# Filtros
st.sidebar.header("Filtros")
cats = sorted(productos["categoria_norm"].unique())
cats_sel = st.sidebar.multiselect("Categorías", cats, default=cats)

todas_tiendas = sorted(productos["tienda"].unique())
tiendas_competencia = [t for t in todas_tiendas if t != "michelle_belau"]
tiendas_comp_sel = st.sidebar.multiselect(
    "Tiendas competencia", tiendas_competencia, default=tiendas_competencia,
    help="Michelle Belau siempre está incluida como referencia.")
tiendas_sel = tiendas_comp_sel + ["michelle_belau"]

tipos_comp = ["Todas"] + [t for t in sorted(productos["competencia"].unique()) if t != "PROPIA"]
comp_sel = st.sidebar.selectbox("Tipo de competencia", tipos_comp)

pmin = float(productos["precio_venta"].min())
pmax = float(productos["precio_venta"].max())
rango = st.sidebar.slider("Rango de precio (S/.)", pmin, pmax, (pmin, pmax))

desc_estado = st.sidebar.radio("Descuento", ["Todos", "Solo con descuento", "Solo sin descuento"])

f = productos[
    productos["categoria_norm"].isin(cats_sel)
    & productos["tienda"].isin(tiendas_sel)
    & productos["precio_venta"].between(*rango)]
if comp_sel != "Todas":
    f = f[(f["competencia"] == comp_sel) | (f["competencia"] == "PROPIA")]
if desc_estado == "Solo con descuento":
    f = f[(f["tiene_descuento"]) | (f["competencia"] == "PROPIA")]
elif desc_estado == "Solo sin descuento":
    f = f[(~f["tiene_descuento"]) | (f["competencia"] == "PROPIA")]

mb      = f[f["competencia"] == "PROPIA"]
mercado = f[f["competencia"] != "PROPIA"]
k1, k2, k3, k4 = st.columns(4)
k1.metric("Productos (filtro)", f"{len(f):,}")
k2.metric("Precio prom. MB", f"S/. {mb['precio_venta'].mean():.0f}" if len(mb) else "—")
k3.metric("Precio prom. mercado", f"S/. {mercado['precio_venta'].mean():.0f}" if len(mercado) else "—")
if len(mb) and len(mercado):
    diff = (mb["precio_venta"].mean() - mercado["precio_venta"].mean()) / mercado["precio_venta"].mean() * 100
    k4.metric("MB vs. mercado", f"{diff:+.0f}%", help="Positivo = MB más cara que el promedio del mercado")
else:
    k4.metric("MB vs. mercado", "—")
st.divider()

if f.empty:
    st.info("Sin datos para los filtros actuales. Ajusta los filtros de la izquierda.")
    st.stop()

t1, t2, t3, t4, t_evo, t5 = st.tabs([
    "Posición por categoría",
    "Productos fuera de rango",
    "Descuentos: MB vs. mercado",
    "Dispersión / oportunidad",
    "Evolución de precios",
    "Explorador",
])

# ===========================================================================
# P1 + P2: Posición por categoría
# ===========================================================================
with t1:
    st.subheader("¿Cómo se posiciona Michelle Belau frente al mercado por categoría?")
    if benchmark.empty:
        st.info("Sin datos de Michelle Belau para comparar.")
    else:
        b = benchmark[benchmark["categoria_norm"].isin(cats_sel)].copy()

        sobre = int((b["mb_vs_mercado_pct"] > 0).sum())
        bajo  = int((b["mb_vs_mercado_pct"] < 0).sum())
        desv_media = float(b["mb_vs_mercado_pct"].mean())
        k1, k2, k3 = st.columns(3)
        k1.metric("Categorías donde MB está más cara", f"{sobre} / {len(b)}",
                  help="Precio promedio de MB > promedio del mercado")
        k2.metric("Categorías donde MB está más barata", f"{bajo} / {len(b)}",
                  help="Precio promedio de MB < promedio del mercado")
        k3.metric("Desviación promedio de MB vs. mercado", f"{desv_media:+.1f}%",
                  help="Desviación del precio promedio de MB respecto al mercado")
        st.divider()

        st.markdown("#### Precio promedio por categoría")
        st.caption("Barras grises = precio promedio del mercado. "
                   "Punto rosa = precio promedio de Michelle Belau. "
                   "La línea punteada muestra el rango (min – max) del mercado.")

        # Primer gráfico: barras del mercado + puntos MB
        fig = px.bar(b, x="categoria_norm", y="mercado_promedio",
                     labels={"categoria_norm": "Categoría", "mercado_promedio": "Precio (S/.)"},
                     color_discrete_sequence=[COLOR_MERCADO],
                     text=b["mercado_promedio"].round(0))
        fig.add_scatter(
            x=b["categoria_norm"], y=b["mb_precio_promedio"],
            mode="markers+text",
            marker=dict(size=14, color=COLOR_MB, symbol="circle"),
            text=b["mb_precio_promedio"].round(0),
            textposition="top center", textfont=dict(color=COLOR_MB, size=11),
            name="Michelle Belau")
        fig.update_traces(selector=dict(type="bar"), textposition="inside",
                          textfont_color="white")
        eje_soles(fig)
        fig.update_xaxes(title_text="Categoría")
        fig.update_layout(height=480, legend_title_text="", showlegend=True, bargap=0.35)
        st.plotly_chart(fig, width='stretch')

        st.divider()
        st.markdown("#### ¿En qué categorías MB está por encima o por debajo del mercado?")
        b["posición"] = b["mb_vs_mercado_pct"].apply(
            lambda x: "⬆️ Por encima" if x > 5 else ("⬇️ Por debajo" if x < -5 else "≈ En línea"))
        b_sorted = b.sort_values("mb_vs_mercado_pct")
        fig2 = px.bar(b_sorted, x="mb_vs_mercado_pct", y="categoria_norm",
                      orientation="h", color="mb_vs_mercado_pct",
                      color_continuous_scale=["#1971c2", "#adb5bd", "#d6336c"],
                      color_continuous_midpoint=0,
                      text=b_sorted["mb_vs_mercado_pct"].apply(lambda x: f"{x:+.1f}%"),
                      labels={"mb_vs_mercado_pct": "MB vs. promedio mercado (%)",
                              "categoria_norm": "Categoría"})
        fig2.update_traces(textposition="outside")
        fig2.add_vline(x=0, line_dash="dash", line_color="gray", line_width=1)
        fig2.update_xaxes(ticksuffix=" %", zeroline=True)
        fig2.update_layout(height=420, showlegend=False, coloraxis_showscale=False,
                           xaxis_range=[b_sorted["mb_vs_mercado_pct"].min() - 15,
                                        b_sorted["mb_vs_mercado_pct"].max() + 15])
        st.plotly_chart(fig2, width='stretch')
        st.caption("Azul = MB más barata · Gris = en línea (±5%) · Rosa = MB más cara")
        st.dataframe(
            b[["categoria_norm", "mb_precio_promedio", "mercado_promedio",
               "mercado_min", "mercado_max", "mb_vs_mercado_pct", "posición"]]
            .rename(columns={"categoria_norm": "Categoría",
                             "mb_precio_promedio": "Precio MB (S/.)",
                             "mercado_promedio": "Prom. mercado (S/.)",
                             "mercado_min": "Mín. mercado (S/.)",
                             "mercado_max": "Máx. mercado (S/.)",
                             "mb_vs_mercado_pct": "MB vs. mercado (%)",
                             "posición": "Posición"})
            .sort_values("MB vs. mercado (%)", ascending=False),
            width='stretch', hide_index=True)

# ===========================================================================
# P3: Productos fuera de rango
# ===========================================================================
with t2:
    st.subheader("¿Qué productos de Michelle Belau están fuera del rango del mercado?")
    if posicion.empty:
        st.info("Sin datos de posicionamiento (requiere productos de MB y del mercado).")
    else:
        p = posicion[posicion["categoria_norm"].isin(cats_sel)].copy()
        fuera = p[p["fuera_de_rango"]]
        n_rango = int((~p["fuera_de_rango"]).sum())
        k1, k2, k3 = st.columns(3)
        k1.metric("Productos MB analizados", len(p))
        k2.metric("Dentro del rango del mercado", n_rango)
        k3.metric("Fuera de rango (candidatos a revisar)", len(fuera),
                  delta=f"{'⚠️ Revisar precios' if len(fuera) > 0 else '✅ Sin alertas'}",
                  delta_color="off")
        st.divider()
        st.caption("Cada punto es un producto de MB. "
                   "Rojo = caro (>2σ del promedio del mercado). "
                   "Azul = barato (<2σ). Gris = dentro del rango típico.")
        fig = px.strip(p, x="categoria_norm", y="precio_venta", color="señal",
                       hover_data={"titulo": True, "vs_promedio_pct": ":.1f%",
                                   "mercado_promedio": ":.0f",
                                   "categoria_norm": False, "señal": False},
                       color_discrete_map={"Caro vs. mercado": "#e03131",
                                           "Barato vs. mercado": "#1971c2",
                                           "En rango": COLOR_MERCADO},
                       labels={"categoria_norm": "Categoría",
                               "precio_venta": "Precio MB (S/.)",
                               "señal": "Posición",
                               "vs_promedio_pct": "vs. prom. mercado",
                               "mercado_promedio": "Prom. mercado (S/.)"},
                       stripmode="overlay")
        # --- CORRECCIÓN 2: observed=True ---
        refs = p.groupby("categoria_norm", observed=True)["mercado_promedio"].first().reset_index()
        fig.add_scatter(x=refs["categoria_norm"], y=refs["mercado_promedio"],
                        mode="markers",
                        marker=dict(symbol="line-ew-open", size=22, color="black",
                                    line=dict(width=2)),
                        name="Promedio mercado")
        eje_soles(fig, "Precio MB (S/.)")
        fig.update_xaxes(title_text="Categoría")
        fig.update_layout(height=480, legend_title_text="")
        st.plotly_chart(fig, width='stretch')
        if fuera.empty:
            st.success("✅ Ningún producto de MB está fuera del rango típico del mercado.")
        else:
            st.markdown(f"**{len(fuera)} producto(s) fuera de rango — candidatos a revisar:**")
            st.dataframe(
                fuera[["titulo", "categoria_norm", "precio_venta",
                       "mercado_promedio", "vs_promedio_pct", "señal"]]
                .rename(columns={"titulo": "Producto", "categoria_norm": "Categoría",
                                 "precio_venta": "Precio MB (S/.)",
                                 "mercado_promedio": "Prom. mercado (S/.)",
                                 "vs_promedio_pct": "vs. prom. (%)", "señal": "Señal"})
                .sort_values("vs. prom. (%)", ascending=False),
                width='stretch', hide_index=True)

# ===========================================================================
# P4: Descuentos MB vs. mercado
# ===========================================================================
with t3:
    st.subheader("¿Michelle Belau descuenta más o menos que la competencia?")
    if descuentos.empty:
        st.info("Sin datos de descuentos.")
    else:
        d = descuentos.copy()
        d_sorted = d.sort_values("pct_en_descuento", ascending=False).reset_index(drop=True)
        pos_mb = int(d_sorted[d_sorted["es_propia"]].index[0]) + 1 if d_sorted["es_propia"].any() else None
        mb_row    = d_sorted[d_sorted["es_propia"]]
        comp_rows = d_sorted[~d_sorted["es_propia"]]
        mb_pct  = float(pd.to_numeric(mb_row["pct_en_descuento"],   errors="coerce").iloc[0]) if pos_mb else None
        mb_prof = float(pd.to_numeric(mb_row["descuento_promedio"], errors="coerce").iloc[0]) if pos_mb else None
        mercado_pct_mean  = float(pd.to_numeric(comp_rows["pct_en_descuento"],   errors="coerce").mean())
        mercado_prof_mean = float(pd.to_numeric(comp_rows["descuento_promedio"], errors="coerce").mean())

        k1, k2, k3 = st.columns(3)
        k1.metric("Posición MB en frecuencia de descuento",
                  f"#{pos_mb} de {len(d)}" if pos_mb else "—",
                  help="1 = el que más descuenta")
        if mb_pct is not None and mb_prof is not None:
            k2.metric("MB: % catálogo en descuento", f"{mb_pct:.1f}%",
                      delta=f"{mb_pct - mercado_pct_mean:+.1f}% vs. promedio mercado",
                      delta_color="off")
            k3.metric("MB: descuento promedio", f"{mb_prof:.1f}%",
                      delta=f"{mb_prof - mercado_prof_mean:+.1f}% vs. promedio mercado",
                      delta_color="off")
        st.divider()

        d["etiqueta"] = d.apply(
            lambda r: f"⭐ {r['tienda']}" if r["es_propia"] else r["tienda"], axis=1)
        c1, c2 = st.columns(2)
        with c1:
            ds = d.sort_values("pct_en_descuento")
            colores = [COLOR_MB if e else COLOR_MERCADO for e in ds["es_propia"]]
            fig = px.bar(ds, x="pct_en_descuento", y="etiqueta", orientation="h",
                         text=ds["pct_en_descuento"].apply(lambda x: f"{x:.1f}%"),
                         labels={"pct_en_descuento": "% del catálogo en descuento", "etiqueta": ""})
            fig.update_traces(marker_color=colores, textposition="outside")
            fig.add_vline(x=mercado_pct_mean, line_dash="dot", line_color="gray",
                          annotation_text=f"Prom. mercado {mercado_pct_mean:.1f}%",
                          annotation_position="top right")
            fig.update_xaxes(ticksuffix=" %", range=[0, ds["pct_en_descuento"].max() + 15])
            fig.update_layout(height=340, title="Frecuencia (% catálogo en oferta)")
            st.plotly_chart(fig, width='stretch')
        with c2:
            ds2 = d.sort_values("descuento_promedio")
            colores2 = [COLOR_MB if e else COLOR_MERCADO for e in ds2["es_propia"]]
            fig2 = px.bar(ds2, x="descuento_promedio", y="etiqueta", orientation="h",
                          text=ds2["descuento_promedio"].apply(lambda x: f"{x:.1f}%"),
                          labels={"descuento_promedio": "Descuento promedio (%)", "etiqueta": ""})
            fig2.update_traces(marker_color=colores2, textposition="outside")
            fig2.add_vline(x=mercado_prof_mean, line_dash="dot", line_color="gray",
                           annotation_text=f"Prom. mercado {mercado_prof_mean:.1f}%",
                           annotation_position="top right")
            fig2.update_xaxes(ticksuffix=" %", range=[0, ds2["descuento_promedio"].max() + 10])
            fig2.update_layout(height=340, title="Profundidad (descuento promedio)")
            st.plotly_chart(fig2, width='stretch')
        st.dataframe(
            d[["tienda", "competencia", "n_productos", "pct_en_descuento", "descuento_promedio"]]
            .rename(columns={"tienda": "Tienda", "competencia": "Tipo",
                             "n_productos": "N° productos",
                             "pct_en_descuento": "% en descuento",
                             "descuento_promedio": "Descuento prom. (%)"})
            .sort_values("% en descuento", ascending=False),
            width='stretch', hide_index=True)

# ===========================================================================
# P5: Dispersión / oportunidad
# ===========================================================================
with t4:
    st.subheader("¿Qué categorías tienen más dispersión de precios (oportunidad)?")
    if dispersion.empty:
        st.info("Sin datos de dispersión.")
    else:
        disp = dispersion[dispersion["categoria_norm"].isin(cats_sel)].copy()
        med_disp = float(disp["dispersion"].median())
        med_desc = float(disp["pct_en_descuento"].median())
        st.caption("**Lectura del gráfico:** cada burbuja es una categoría del mercado. "
                   "Eje X = dispersión de precios. Eje Y = % del mercado en descuento. "
                   "Tamaño = nº de productos.")
        k1, k2 = st.columns(2)
        k1.info("↗️ **Alta dispersión + mucho descuento** → mercado dinámico, "
                "márgenes bajo presión. MB debe ser selectiva con sus descuentos.")
        k2.info("↘️ **Alta dispersión + poco descuento** → mayor margen para "
                "posicionar precio sin necesidad de descuento.")
        fig = px.scatter(disp, x="dispersion", y="pct_en_descuento",
                         size="n_productos", color="categoria_norm", text="categoria_norm",
                         color_discrete_sequence=PALETA,
                         hover_data={"precio_promedio": ":.0f", "precio_min": ":.0f",
                                     "precio_max": ":.0f", "n_productos": True,
                                     "dispersion": ":.0f", "pct_en_descuento": ":.1f"},
                         labels={"dispersion": "Dispersión de precio (S/.)",
                                 "pct_en_descuento": "% mercado en descuento",
                                 "categoria_norm": "Categoría", "n_productos": "N° productos",
                                 "precio_promedio": "Precio prom. (S/.)",
                                 "precio_min": "Mín. (S/.)", "precio_max": "Máx. (S/.)"})
        fig.add_vline(x=med_disp, line_dash="dot", line_color="lightgray", line_width=1)
        fig.add_hline(y=med_desc, line_dash="dot", line_color="lightgray", line_width=1)
        xmax = float(disp["dispersion"].max())
        ymax = float(disp["pct_en_descuento"].max())
        ymin = float(disp["pct_en_descuento"].min())
        for texto, x, y, anchor in [
            ("Dinámico · presión en márgenes",       xmax * 0.98, ymax * 0.98,            "right"),
            ("Oportunidad · posicionar sin descuento", xmax * 0.98, ymin + (med_desc - ymin) * 0.1, "right"),
            ("Precios uniformes · descuento frecuente", med_disp * 0.05, ymax * 0.98,     "left"),
            ("Precios uniformes · estable",            med_disp * 0.05, ymin + (med_desc - ymin) * 0.1, "left"),
        ]:
            fig.add_annotation(x=x, y=y, text=texto, showarrow=False,
                               font=dict(size=10, color="gray"), xanchor=anchor)
        fig.update_traces(textposition="top center", textfont_size=11)
        fig.update_xaxes(tickprefix="S/. ")
        fig.update_yaxes(ticksuffix=" %")
        fig.update_layout(showlegend=False, height=530)
        st.plotly_chart(fig, width='stretch')
        st.markdown("#### Detalle por categoría")
        st.dataframe(
            disp[["categoria_norm", "precio_promedio", "dispersion",
                  "precio_min", "precio_max", "n_productos", "pct_en_descuento"]]
            .rename(columns={"categoria_norm": "Categoría",
                             "precio_promedio": "Precio prom. (S/.)",
                             "dispersion": "Dispersión (S/.)",
                             "precio_min": "Mín. (S/.)", "precio_max": "Máx. (S/.)",
                             "n_productos": "N° productos",
                             "pct_en_descuento": "% mercado en descuento"})
            .sort_values("Dispersión (S/.)", ascending=False),
            width='stretch', hide_index=True)

# ===========================================================================
# Evolución temporal
# ===========================================================================
with t_evo:
    st.subheader("Evolución de precios en el tiempo: Michelle Belau vs. mercado")
    if historico.empty:
        st.info("Aún no hay histórico. Se construye acumulando corridas diarias. "
                "Con 2 o más fechas, aquí verás la evolución de precios.")
    else:
        # normalizar fecha SIEMPRE antes de cualquier operación
        h = historico.copy()
        h["fecha"] = h["fecha"].astype(str).str[:10]
        n_fechas = h["fecha"].nunique()
 
        if n_fechas < 2:
            st.warning(f"Solo hay datos de 1 fecha ({h['fecha'].iloc[0]}). "
                       "La evolución aparecerá cuando haya al menos 2 corridas en días distintos.")
            st.dataframe(h.rename(columns={
                "fecha": "Fecha", "categoria_norm": "Categoría",
                "serie": "Serie", "precio_promedio": "Precio prom. (S/.)"}),
                width='stretch', hide_index=True)
        else:
            cat_evo = st.selectbox(
                "Categoría a visualizar",
                ["(TODAS)"] + sorted(
                    h[~h["categoria_norm"].isin(["TODAS"])]["categoria_norm"].unique()))
 
            if cat_evo == "(TODAS)":
                tiene_todas = (h["categoria_norm"] == "TODAS").any()
                if tiene_todas:
                    # promedio ponderado pre-calculado en gold
                    h_plot = h[h["categoria_norm"] == "TODAS"].copy()
                else:
                    # fallback: promedio de todos los productos por fecha
                    h_plot = h[h["categoria_norm"].isin(cats_sel)].copy()
                    h_plot = h_plot.groupby(["fecha", "serie"],
                                            observed=True)["precio_promedio"].mean().reset_index()
            else:
                h_plot = h[h["categoria_norm"] == cat_evo].copy()
 
            h_plot = h_plot.groupby(["fecha", "serie"],
                                    observed=True)["precio_promedio"].mean().reset_index()
            h_plot["fecha"] = h_plot["fecha"].astype(str).str[:10]
 
            fig = px.line(h_plot, x="fecha", y="precio_promedio", color="serie",
                          markers=True,
                          color_discrete_map={"Michelle Belau": COLOR_MB,
                                              "Mercado": COLOR_MERCADO},
                          labels={"fecha": "Fecha",
                                  "precio_promedio": "Precio promedio (S/.)", "serie": ""})
            eje_soles(fig, "Precio promedio (S/.)")
            fig.update_xaxes(title_text="Fecha", type="category")
            fig.update_layout(height=460, legend_title_text="",
                              title=f"Precio promedio · {cat_evo}")
            st.plotly_chart(fig, width='stretch')
            st.caption("Línea rosa = Michelle Belau · Línea gris = promedio del mercado. "
                       "Cada punto = una corrida del pipeline.")

# ===========================================================================
# Explorador
# ===========================================================================
with t5:
    st.subheader("Explorador de catálogo")
    solo_mb = st.checkbox("Solo Michelle Belau")
    vista = f[f["competencia"] == "PROPIA"] if solo_mb else f
    st.caption(f"{len(vista):,} productos con los filtros actuales.")
    st.dataframe(
        vista[["tienda", "competencia", "titulo", "categoria_norm",
               "precio_venta", "precio_etiqueta", "descuento_pct",
               "rango_precio", "rango_descuento"]]
        .rename(columns={"tienda": "Tienda", "competencia": "Tipo",
                         "titulo": "Producto", "categoria_norm": "Categoría",
                         "precio_venta": "Precio (S/.)",
                         "precio_etiqueta": "Precio lista (S/.)",
                         "descuento_pct": "Descuento (%)",
                         "rango_precio": "Rango precio",
                         "rango_descuento": "Rango descuento"})
        .sort_values("Precio (S/.)", ascending=False),
        width='stretch', hide_index=True)
