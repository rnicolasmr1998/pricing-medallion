# Pricing Intelligence — Arquitectura Medallón

Sistema automatizado de monitoreo de precios de la competencia en el retail
textil peruano. Ingiere el catálogo de tiendas competidoras, lo limpia y
normaliza, y produce agregados de negocio que alimentan una Data App
interactiva en Streamlit.

Implementado sobre la **arquitectura medallón** (bronce → plata → oro), donde
cada capa transforma el dato dejándolo más limpio y más cerca de responder
las preguntas de negocio.

---

## Objetivo

### Objetivo principal
Automatizar el monitoreo de precios de la competencia para convertir
información pública dispersa en un activo de datos estructurado y confiable,
que habilite decisiones de pricing en Michelle Belau — es decir, fijar precios
y descuentos con base en el mercado, no por intuición.

### Objetivos específicos
- **Ingesta automatizada** del catálogo de competidores, con manejo de errores
  y almacenamiento en formatos optimizados.
- **Equivalencia de categorías**: traducir las categorías de cada competidor a
  una taxonomía propia, para comparar prenda contra prenda.
- **Modelo analítico limpio y validado**, listo para análisis y BI.
- **Inteligencia comercial**: benchmark de precios por categoría e intensidad
  de descuento por competidor.
- **Data App** para explorar los datos y apoyar la toma de decisiones.

## Preguntas de negocio

Michelle Belau se ingiere como una tienda más (etiquetada `PROPIA`) y sirve de
punto de comparación contra el mercado (competencia `DIRECTA` + `INDIRECTA`).
Todas las preguntas se responden **solo con datos web** (precio, descuento,
categoría):

1. ¿Cómo se posiciona Michelle Belau frente a la competencia por categoría?
2. ¿En qué categorías MB está por encima o por debajo del precio promedio del
   mercado?
3. ¿Qué productos de MB están fuera del rango de precio típico de su categoría
   en el mercado?
4. ¿MB descuenta más o menos (frecuencia y profundidad) que la competencia?
5. ¿Qué categorías tienen mayor dispersión de precios en el mercado (margen de
   maniobra para posicionar)?

*Fuera de alcance con datos web*: margen, rotación, descuento óptimo y
elasticidad requieren datos internos de ventas y costo, que no forman parte de
este pipeline.

---

## Arquitectura medallón

```
   FUENTES                BRONCE              PLATA               ORO            DATA APP
 (5 tiendas Shopify)   (bruto, Avro+Parquet)   (limpio, Parquet)  (agregado, Parquet)  (Streamlit)
        |                    |                  |                   |               |
   API products.json  →  ingesta sin    →  aplana, limpia,   →  resúmenes de   →  filtros,
                          transformar       valida, reglas       negocio en        gráficos,
                          (JSON crudo)       de negocio,          soles             KPIs
                                             normaliza cat.
```

### Capa BRONCE — `pipeline/bronze.py`
Ingesta **totalmente automatizada** desde la API de cada tienda Shopify
(`/collections/all/products.json`, paginada). Guarda la respuesta **tal cual**
(JSON crudo) en formato **Arrow/Feather**, una fila por página con metadatos.

- **Fuente**: API REST (JSON) de 5 tiendas Shopify.
- **Formato**: se guarda en **Avro** (fila, ideal para archivar el JSON crudo
  de ingesta) y **Parquet** (columnar, para releer rápido en la capa silver).
- **Manejo de errores**: cada tienda se ingiere aislada; si una falla, se
  registra en el manifiesto y las demás continúan. Reintentos automáticos con
  backoff ante errores transitorios (429/5xx).
- **Fidelidad**: se guarda el JSON íntegro, así se puede reprocesar todo aguas
  abajo sin volver a descargar.

### Capa PLATA — `pipeline/silver.py`
Limpieza, transformación y validación avanzadas. Produce un dataset limpio,
tipado y validado en **Parquet**. Transformaciones (documentadas en orden en
el propio módulo):

1. **Aplanado**: de JSON anidado (producto → variantes) a **una fila por
   producto**. Se toma la primera variante porque el precio no cambia por
   talla → no se infla la base con duplicados.
2. **Parseo de precios a céntimos** (entero) → exactitud en cálculos.
3. **Manejo de valores faltantes**:
   - Sin precio de venta → se descarta (un producto sin precio no sirve para
     pricing).
   - Sin precio de etiqueta → se asume igual al de venta (sin descuento).
   - Sin categoría → "NO INDICA".
4. **Reglas de negocio**: `descuento_pct`, `tiene_descuento`,
   `monto_ahorro_centimos`.
5. **Normalización de categorías** → taxonomía propia (`categoria_norm`), vía
   `config/categorias_map.csv`. Las categorías no mapeadas se registran en
   `logs/sin_mapear.csv` para revisión (no se inventan).
6. **Optimización de recursos**: downcasting de enteros y `category` en
   columnas de baja cardinalidad, para reducir memoria.
7. **Validación con pandera**: contrato de tipos y rangos (precio > 0,
   descuento 0–100, competencia ∈ {DIRECTA, INDIRECTA}...). Si algo no cumple,
   la capa falla y no contamina el análisis.

### Capa ORO — `pipeline/gold.py`
Agrega el dato limpio en tablas que responden directo las preguntas de
negocio, **en soles**. Michelle Belau (`PROPIA`) se compara contra el mercado:

- `gold_productos.parquet` — detalle de todas las tiendas con binning de precio
  (cuartiles) y de descuento (tramos fijos). Base del explorador.
- `gold_benchmark_categoria.parquet` — precio de MB vs. mercado por categoría
  (P1, P2).
- `gold_posicionamiento_producto.parquet` — cada producto de MB ubicado en el
  rango del mercado, con marca de fuera-de-rango (P3).
- `gold_descuentos_tienda.parquet` — frecuencia y profundidad de descuento por
  tienda, con MB marcada (P4).
- `gold_dispersion_categoria.parquet` — dispersión de precios del mercado por
  categoría (P5).
- `gold_historico_precios.parquet` — **acumulativo**: precio promedio de MB y
  del mercado por categoría y fecha. Habilita la evolución temporal en la app.

Reglas de binning: `rango_precio` por cuartiles (Económico/Medio/Premium/Lujo);
`rango_descuento` por tramos fijos (Sin descuento/Moderado/Agresivo/Liquidación).

### Data App — `app/app.py`
Streamlit sobre la capa oro. Filtros (multiselect de tiendas y categorías,
radio de tipo de competencia, slider de precio, checkbox de solo-descuento),
4 KPIs, y 3 pestañas: Benchmark por categoría, Descuentos por tienda, y
Explorador de productos.

---

## Convención de precios

Los precios se manejan como **enteros de céntimos** (S/. 349.00 → 34900) en
bronce y plata, por exactitud en sumas y comparaciones (el float binario
introduce errores). Se convierten a **soles** solo en la capa oro / Data App,
donde se leen. Toda columna en céntimos lleva el sufijo `_centimos`.

---

## Estructura

```
pricing-medallion/
├── main.py                     ← orquestador (bronce → plata → oro)
├── requirements.txt
├── config/
│   ├── tiendas.py              ← registro de tiendas (fuentes)
│   ├── settings.py             ← rutas y constantes
│   └── categorias_map.csv      ← equivalencias categoría cruda → taxonomía propia
├── core/
│   ├── transform.py            ← funciones puras (precios, descuento)
│   ├── normalize.py            ← normalización de categorías
│   ├── http_client.py           ← sesión HTTP con reintentos
│   ├── logger.py                ← logging
│   └── manifiesto.py            ← registro de corridas (JSONL)
├── pipeline/
│   ├── bronze.py               ← ingesta bruta → Arrow
│   ├── silver.py               ← limpieza/validación → Parquet
│   └── gold.py                  ← agregados de negocio → Parquet
├── app/
│   └── app.py                  ← Data App Streamlit
├── data/
│   ├── bronze/                 ← crudo por tienda y fecha (Avro + Parquet)
│   ├── silver/                 ← Parquet limpio por fecha
│   └── gold/                    ← Parquet agregado (3 tablas)
└── logs/
    ├── pipeline.log / errores.log
    ├── manifiesto.jsonl        ← una línea por corrida (capa, tienda, filas, estado)
    └── sin_mapear.csv          ← categorías pendientes de mapear
```

---

## Instalación

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

```bash
# Pipeline completo (las 3 capas en orden)
python main.py

# Una sola capa
python main.py --solo bronze
python main.py --solo silver
python main.py --solo gold

# Desde una capa en adelante (ej. reprocesar sin re-descargar)
python main.py --desde silver
```

**Regla de seguridad**: si una capa falla, no se ejecutan las siguientes (no
tiene sentido procesar sobre datos incompletos). Como bronce guarda el crudo,
se puede reprocesar plata/oro las veces que haga falta —al afinar el mapa de
categorías o los umbrales de binning— sin volver a golpear a los competidores.

## Data App

```bash
streamlit run app/app.py
```

Requiere haber corrido el pipeline antes (necesita las tablas en `data/gold/`).

## Despliegue

La Data App se despliega en **Streamlit Community Cloud**: subir el repo a
GitHub, conectar en share.streamlit.io apuntando a `app/app.py`. El pipeline
(`main.py`) se programa aparte como tarea recurrente (ej. Programador de tareas
de Windows o cron) para actualizar las capas a diario.

---

## Mantenimiento del mapa de categorías

Cuando la capa plata encuentra una categoría cruda que no está en
`config/categorias_map.csv`, la marca `SIN_MAPEAR` y la registra en
`logs/sin_mapear.csv`. Flujo: revisar ese archivo, decidir la `categoria_norm`
de cada fila y agregarla al mapa. Luego `python main.py --solo silver`
(y `--solo gold`) para reprocesar, sin re-descargar.

## Pendiente (no implementado aún)

Otras plataformas ya estudiadas para incorporación futura: VTEX (Calvin Klein,
Tommy, Kids Made Here), HCL/Zara, SFCC/Desigual. Su ingesta viviría en la capa
bronce reutilizando el resto del pipeline sin cambios.
