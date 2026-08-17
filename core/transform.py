"""
Funciones puras de transformación (sin red ni disco). Base de la capa SILVER.

CONVENCIÓN DE PRECIOS: se manejan como ENTERO de céntimos (S/. 349.00 -> 34900)
en bronce y silver, por exactitud en sumas/comparaciones (el float binario
introduce errores). Solo se convierte a soles en gold / la Data App.
Toda columna en céntimos lleva el sufijo _centimos.

Correr `python core/transform.py` para probar.
"""

import re

FORMATO_PERUANO = "peruano"   # "S/. 1,169.00" -> coma=miles, punto=decimal
FORMATO_ESPANOL = "espanol"   # "S/. 1.079,00" -> punto=miles, coma=decimal


def parsear_precio_centimos(texto, formato=FORMATO_PERUANO):
    """'S/. 1,169.00' -> 116900. Devuelve None si no hay número válido."""
    if texto is None:
        return None
    texto = str(texto)
    if formato == FORMATO_PERUANO:
        limpio = texto.replace(",", "")
    elif formato == FORMATO_ESPANOL:
        limpio = texto.replace(".", "").replace(",", ".")
    else:
        raise ValueError(f"Formato desconocido: {formato!r}")
    m = re.search(r"\d+(?:\.\d+)?", limpio)
    if not m:
        return None
    try:
        return int(round(float(m.group(0)) * 100))
    except ValueError:
        return None


def a_centimos(valor):
    """Normaliza a entero de céntimos un precio que ya viene en céntimos (Zara)."""
    if not valor:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def centimos_a_soles(centimos):
    """Solo presentación (gold / app): 34900 -> 349.0."""
    if centimos is None:
        return None
    return round(int(centimos) / 100, 2)


def calcular_descuento(precio_venta_centimos, precio_etiqueta_centimos):
    """% entero. 0 si no hay etiqueta o es <= al precio de venta (nunca negativo)."""
    if not precio_venta_centimos or not precio_etiqueta_centimos:
        return 0
    if precio_etiqueta_centimos <= precio_venta_centimos:
        return 0
    return round((precio_etiqueta_centimos - precio_venta_centimos)
                 / precio_etiqueta_centimos * 100)


def categoria_desde_url(url, patron="mujer"):
    """/p/{patron}/{cat}/{subcat}/... -> (cat, subcat) o (None, None)."""
    if not url:
        return None, None
    m = re.search(rf"/p/{re.escape(patron)}/([^/]+)/([^/]+)/", url)
    if not m:
        return None, None
    return m.group(1), m.group(2)


if __name__ == "__main__":
    assert parsear_precio_centimos("S/. 1,169.00") == 116900
    assert parsear_precio_centimos("S/. 899.90") == 89990
    assert parsear_precio_centimos("S/. 1.079,00", FORMATO_ESPANOL) == 107900
    assert parsear_precio_centimos(None) is None
    assert parsear_precio_centimos("agotado") is None
    print("parsear_precio_centimos: OK")

    assert a_centimos(34900) == 34900
    assert a_centimos(0) is None
    print("a_centimos: OK")

    assert centimos_a_soles(34900) == 349.0
    print("centimos_a_soles: OK")

    assert calcular_descuento(12900, 34900) == 63
    assert calcular_descuento(23999, 39999) == 40
    assert calcular_descuento(34900, 34900) == 0
    assert calcular_descuento(10000, None) == 0
    print("calcular_descuento: OK")

    print("\nTodas las pruebas de transform.py pasaron.")
