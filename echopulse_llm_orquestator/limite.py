# limite.py - Control de abuso para la demo pública
"""Ventana deslizante de accesos por IP, sin dependencias de torch.

Cada turno de chat cuesta entre 6 y 10 s de CPU en la VM de 2 núcleos (los dos
transformers más Qwen). Media docena de visitantes impacientes alcanzan para
saturar la máquina y poner al resto en cola, así que la demo frena por IP antes
de ponerse a trabajar.
"""

from __future__ import annotations

import time
from threading import Lock

# Techo de IPs recordadas: con esto la tabla no crece sin límite si alguien
# rota direcciones de origen.
MAX_IPS_VIGILADAS = 5000


class LimitadorVentana:
    """Autoriza hasta `limite` accesos por clave dentro de los últimos `ventana` segundos."""

    def __init__(self, limite: int = 12, ventana: float = 60.0):
        self.limite = limite
        self.ventana = ventana
        self._accesos: dict[str, list[float]] = {}
        self._lock = Lock()

    def permitir(self, clave: str, ahora: float | None = None) -> bool:
        if self.limite <= 0:  # 0 o negativo = sin freno (desarrollo local)
            return True
        ahora = time.time() if ahora is None else ahora
        with self._lock:
            vivos = [t for t in self._accesos.get(clave, ()) if ahora - t < self.ventana]
            bloqueado = len(vivos) >= self.limite
            if not bloqueado:
                vivos.append(ahora)
            self._accesos[clave] = vivos
            self._podar(ahora)
        return not bloqueado

    def _podar(self, ahora: float):
        if len(self._accesos) <= MAX_IPS_VIGILADAS:
            return
        viejas = [k for k, v in self._accesos.items() if not v or ahora - v[-1] >= self.ventana]
        for clave in viejas:
            self._accesos.pop(clave, None)
