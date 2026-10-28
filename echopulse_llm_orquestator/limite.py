# limite.py - Control de abuso para la demo pública
"""Ventana deslizante de accesos por IP, sin dependencias de torch.

Cada turno de chat cuesta entre 6 y 10 s de CPU en la VM de 2 núcleos (los dos
transformers más Qwen). Media docena de visitantes impacientes alcanzan para
saturar la máquina y poner al resto en cola, así que la demo frena por IP antes
de ponerse a trabajar.
"""

from __future__ import annotations

import ipaddress
import time
from threading import Lock

# Techo de IPs recordadas: con esto la tabla no crece sin límite si alguien
# rota direcciones de origen.
MAX_IPS_VIGILADAS = 5000


def _es_proxy_local(direccion: str) -> bool:
    """True si la conexión viene de una red que no puede ser un cliente de internet.

    Se usa `is_global` y no `is_private` porque el conjunto de direcciones
    reservadas (loopback, link-local, CGNAT, rangos de documentación) es lo que de
    verdad distingue al túnel ngrok de un visitante real.
    """
    try:
        return not ipaddress.ip_address(direccion).is_global
    except ValueError:
        return False


def ip_cliente(remote_addr: str | None, x_forwarded_for: str | None) -> str:
    """De quién es la petición, distinguiendo visita directa de visita tras proxy.

    Con el túnel ngrok el TLS termina fuera del contenedor y la conexión llega
    desde la red Docker: si solo se mirara `remote_addr`, todos los visitantes
    compartirían el mismo cubo del límite. La cabecera `X-Forwarded-For` solo se
    cree cuando quien llama ya es el proxy, porque si no cualquiera la inventa
    para saltarse el freno.
    """
    origen = (remote_addr or "").strip()
    if x_forwarded_for and _es_proxy_local(origen):
        primero = x_forwarded_for.split(",")[0].strip()
        if primero:
            return primero
    return origen or "desconocida"


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
