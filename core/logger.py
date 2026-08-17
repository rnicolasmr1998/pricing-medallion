"""
Logging centralizado: consola + archivo general + archivo solo-errores.
"""

import logging
import os

from config.settings import LOGS_DIR

_FORMATO = "%(asctime)s | %(levelname)-8s | %(name)-18s | %(message)s"
_FECHA = "%Y-%m-%d %H:%M:%S"


def get_logger(nombre: str) -> logging.Logger:
    logger = logging.getLogger(nombre)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(_FORMATO, datefmt=_FECHA)

    consola = logging.StreamHandler()
    consola.setLevel(logging.INFO)
    consola.setFormatter(fmt)
    logger.addHandler(consola)

    gen = logging.FileHandler(os.path.join(LOGS_DIR, "pipeline.log"), encoding="utf-8")
    gen.setLevel(logging.DEBUG)
    gen.setFormatter(fmt)
    logger.addHandler(gen)

    err = logging.FileHandler(os.path.join(LOGS_DIR, "errores.log"), encoding="utf-8")
    err.setLevel(logging.WARNING)
    err.setFormatter(fmt)
    logger.addHandler(err)

    return logger
