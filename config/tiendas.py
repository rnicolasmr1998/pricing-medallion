"""
Registro de tiendas competidoras (fuentes de la capa BRONCE).

Agregar una tienda Shopify nueva = agregar una entrada acá. La ingesta la
recorre automáticamente.
"""

TIENDAS_SHOPIFY = [
    {
        "nombre": "michelle_belau",
        "competencia": "PROPIA",
        "plataforma": "shopify",
        "base_url": "https://michellebelau.com/collections/all/products.json",
    },
    {
        "nombre": "mentha_chocolate",
        "competencia": "DIRECTA",
        "plataforma": "shopify",
        "base_url": "https://mch.com.pe/collections/all/products.json",
    },
    {
        "nombre": "ecru",
        "competencia": "DIRECTA",
        "plataforma": "shopify",
        "base_url": "https://www.ecru.pe/collections/all-products/products.json",
    },
    {
        "nombre": "amalfitana",
        "competencia": "DIRECTA",
        "plataforma": "shopify",
        "base_url": "https://amalfitanaitaly.com/collections/all/products.json",
    },
    {
        "nombre": "bassika",
        "competencia": "DIRECTA",
        "plataforma": "shopify",
        "base_url": "https://bassika.pe/collections/all/products.json",
    },
    {
        "nombre": "exit",
        "competencia": "INDIRECTA",
        "plataforma": "shopify",
        "base_url": "https://exit.com.pe/collections/all/products.json",
    },
]
