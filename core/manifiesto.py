"""
Registro de corridas (manifiesto JSONL) y cronómetro, compartidos por las capas.
Una línea por (capa, tienda, corrida): permite auditar qué pasó cada día sin
leer el log completo.
"""

import json
import time
from datetime import datetime

from config.settings import MANIFIESTO_PATH


def registrar_corrida(capa, tienda, competencia, plataforma, filas,
                      duracion_seg, estado, mensaje_error=None):
    registro = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "capa": capa,
        "tienda": tienda,
        "competencia": competencia,
        "plataforma": plataforma,
        "filas": filas,
        "duracion_seg": round(duracion_seg, 2),
        "estado": estado,
        "mensaje_error": mensaje_error,
    }
    with open(MANIFIESTO_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return registro


class Cronometro:
    def __enter__(self):
        self.inicio = time.time()
        return self

    def __exit__(self, *args):
        self.duracion = time.time() - self.inicio
