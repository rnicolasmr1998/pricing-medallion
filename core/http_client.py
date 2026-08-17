"""
Cliente HTTP compartido: sesión con headers de navegador y reintentos
automáticos (backoff) ante errores transitorios (429/5xx).
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.settings import HEADERS, HTTP_TIMEOUT, HTTP_REINTENTOS, HTTP_BACKOFF


def crear_sesion() -> requests.Session:
    sesion = requests.Session()
    sesion.headers.update(HEADERS)
    retry = Retry(
        total=HTTP_REINTENTOS,
        backoff_factor=HTTP_BACKOFF,           # 2s, 4s, 8s...
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adaptador = HTTPAdapter(max_retries=retry)
    sesion.mount("https://", adaptador)
    sesion.mount("http://", adaptador)
    return sesion


def get_json(sesion, url, params=None, logger=None):
    """GET que devuelve JSON o None si falla (loguea el motivo)."""
    if logger:
        logger.debug(f"GET {url} params={params}")
    try:
        resp = sesion.get(url, params=params, timeout=HTTP_TIMEOUT)
    except requests.exceptions.RequestException as e:
        if logger:
            logger.error(f"Error de conexión en {url}: {e}")
        return None
    if resp.status_code not in (200, 206):
        if logger:
            logger.warning(f"HTTP {resp.status_code} en {url}")
        return None
    try:
        return resp.json()
    except ValueError:
        if logger:
            logger.error(f"Respuesta no es JSON válido en {url}")
        return None
