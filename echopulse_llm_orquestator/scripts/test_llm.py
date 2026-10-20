# test_llm.py - Pruebas sin red de la capa LLM y del motor conversacional
"""
Se ejecuta con:

    python scripts/test_llm.py

No necesita internet ni modelos: levanta un servidor HTTP local que imita
`/v1/chat/completions` y comprueba lo que fallaba en producción:

  * un 402 (HF sin créditos) NO se reintenta y se salta al siguiente proveedor,
  * un 429 con Retry-After se reintenta una sola vez,
  * la salida de Qwen3 (` thinking...`) se limpia antes de mostrarse,
  * las keywords en español que inventa un modelo pequeño se rechazan,
  * el motor determinista conversa (cita canciones, no repite, cierra con pregunta).
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import conversacion as conv  # noqa: E402
from llm_client import ClienteLLM, Proveedor, limpiar_salida  # noqa: E402

# ---------------------------------------------------------------------------
# Servidor de mentira con el protocolo OpenAI
# ---------------------------------------------------------------------------
RESPUESTAS_POR_RUTA: dict[str, list[int]] = {}
CONTADOR: dict[str, int] = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):  # silencio
        pass

    def do_POST(self):  # noqa: N802
        largo = int(self.headers.get("Content-Length", 0))
        self.rfile.read(largo)
        ruta = self.path
        indice = CONTADOR.get(ruta, 0)
        CONTADOR[ruta] = indice + 1
        estados = RESPUESTAS_POR_RUTA.get(ruta, [200])
        estado = estados[min(indice, len(estados) - 1)]

        if estado == 200:
            cuerpo = {"choices": [{"message": {"role": "assistant", "content": "ok desde el stub"}}]}
            self._responder(200, cuerpo)
        elif estado == 402:
            self._responder(402, {"error": "You have no remaining credits."})
        elif estado == 429:
            self._responder(429, {"error": "rate limited"}, {"Retry-After": "0"})
        else:
            self._responder(estado, {"error": "boom"})

    def _responder(self, estado: int, cuerpo: dict, headers: dict | None = None):
        datos = json.dumps(cuerpo).encode()
        self.send_response(estado)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        for clave, valor in (headers or {}).items():
            self.send_header(clave, valor)
        self.end_headers()
        self.wfile.write(datos)


def arrancar_servidor() -> tuple[ThreadingHTTPServer, str]:
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    return servidor, f"http://127.0.0.1:{servidor.server_port}/v1"


# ---------------------------------------------------------------------------
# Pruebas
# ---------------------------------------------------------------------------
def test_limpieza_think():
    crudo = "<think>El usuario pide rock pesado.</think>Claro, te recomiendo «Matilda» de Alt-J."
    limpio = limpiar_salida(crudo)
    assert "think" not in limpio.lower(), limpio
    assert limpio.startswith("Claro"), limpio


def test_402_salta_al_siguiente():
    servidor, base = arrancar_servidor()
    try:
        RESPUESTAS_POR_RUTA.clear()
        CONTADOR.clear()
        RESPUESTAS_POR_RUTA["/v1/sin-creditos/chat/completions"] = [402]
        RESPUESTAS_POR_RUTA["/v1/sano/chat/completions"] = [200]

        caido = Proveedor(nombre="hf_caido", base_url=f"{base}/sin-creditos", modelo="Qwen/Qwen3-4B")
        sano = Proveedor(nombre="local", base_url=f"{base}/sano", modelo="qwen2.5")
        cliente = ClienteLLM([caido, sano], log=lambda *_: None)

        salida = cliente.chat([{"role": "user", "content": "hola"}], max_tokens=10)
        assert salida is not None and salida.proveedor == "local", salida
        # El 402 se marcó como caído y no se volvió a llamar
        assert CONTADOR["/v1/sin-creditos/chat/completions"] == 1, CONTADOR
        estado = cliente.estado()
        assert "hf_caido" in estado["caidos"], estado
        assert "You have no remaining credits" in estado["caidos"]["hf_caido"]["motivo"], estado
        print("✅ 402 no se reintenta y se salta al proveedor sano")
    finally:
        servidor.shutdown()


def test_429_reintenta_una_vez():
    servidor, base = arrancar_servidor()
    try:
        RESPUESTAS_POR_RUTA.clear()
        CONTADOR.clear()
        RESPUESTAS_POR_RUTA["/v1/limitado/chat/completions"] = [429, 200]
        proveedor = Proveedor(nombre="limitado", base_url=f"{base}/limitado", modelo="qwen")
        cliente = ClienteLLM([proveedor], log=lambda *_: None)
        salida = cliente.chat([{"role": "user", "content": "hola"}], max_tokens=10)
        assert salida is not None, "el reintento tras 429 debería funcionar"
        assert CONTADOR["/v1/limitado/chat/completions"] == 2, CONTADOR
        print("✅ 429 con Retry-After se reintenta exactamente una vez")
    finally:
        servidor.shutdown()


def test_todos_caidos():
    servidor, base = arrancar_servidor()
    try:
        RESPUESTAS_POR_RUTA.clear()
        CONTADOR.clear()
        RESPUESTAS_POR_RUTA["/v1/roto/chat/completions"] = [500]
        proveedor = Proveedor(nombre="roto", base_url=f"{base}/roto", modelo="qwen")
        cliente = ClienteLLM([proveedor], log=lambda *_: None)
        assert cliente.chat([{"role": "user", "content": "hola"}]) is None
        assert cliente.activo is False
        print("✅ Si todo falla devuelve None (y el agente cae al motor determinista)")
    finally:
        servidor.shutdown()


def test_clasificacion_y_tono():
    assert conv.clasificar_mensaje("hola") == "saludo"
    assert conv.clasificar_mensaje("me siento triste y aburrido") == "musica"
    assert conv.clasificar_mensaje("¿tú qué preferirías si es un artista nuevo?") == "pregunta"
    assert conv.clasificar_mensaje("dame algo más parecido") == "mas_de_lo_mismo"
    clave, _, keywords = conv.detectar_tono("quiero algo de rock pesado")
    assert clave == "rock" and "rock" in keywords, (clave, keywords)
    clave, _, keywords = conv.detectar_tono("ahora quiero algo fiestero")
    assert clave == "fiesta" and "party" in keywords, (clave, keywords)
    print("✅ Clasificación de turno y detección de tono")


def test_respuesta_determinista():
    canciones = [
        {"track_name": "Matilda", "artist_name": "Alt-J"},
        {"track_name": "Gimme Some Lovin'", "artist_name": "The Spencer Davis Group"},
        {"track_name": "Unknown", "artist_name": "Unknown"},
    ]
    sesion = {"turnos": 0, "ultimos_nombres": []}

    r1 = conv.respuesta_determinista("me siento triste y aburrido", canciones, sesion)
    assert "Matilda" in r1 and "Gimme Some Lovin'" in r1, r1
    assert "Unknown" not in r1, r1
    assert r1.rstrip().endswith("?"), r1
    assert not r1.startswith("Además"), "la primera respuesta no debe empezar con 'Además'"

    r2 = conv.respuesta_determinista(
        "¿tú qué preferirías si es un artista nuevo?",
        canciones,
        {"turnos": 2, "ultimos_nombres": ["Matilda"]},
    )
    assert r2.rstrip().endswith("?"), r2
    assert "Matilda" in r2 or "Gimme" in r2, r2

    r3 = conv.respuesta_determinista("otra tanda parecida", canciones, {"turnos": 3, "ultimos_nombres": ["Matilda"]})
    assert "Matilda" in r3, r3

    r4 = conv.respuesta_determinista("hola", canciones, {"turnos": 4})
    assert "Hola" in r4, r4
    print("✅ Respuestas deterministas: contextuales, sin 'Unknown' y con pregunta final")


def test_historial_como_turnos():
    historial = [
        {"role": "user", "content": "quiero rock"},
        {"role": "assistant", "content": "te va «Matilda»"},
    ]
    mensajes = conv.construir_mensajes("eres EchoPulse", historial, "dame más", max_turnos=8)
    assert mensajes[0]["role"] == "system"
    assert [m["role"] for m in mensajes[1:]] == ["user", "assistant", "user"]
    assert mensajes[-1]["content"] == "dame más"
    print("✅ El historial se envía como turnos reales de chat")


def test_validar_keywords():
    # Lo que devolvió Qwen 1.5B a una pregunta: no son keywords, se rechaza
    assert conv.validar_keywords_en("entendido, que es muy popular y tiene un ritmo") is None
    assert conv.validar_keywords_en("perfecto, para una tanda tranquila") is None
    assert conv.validar_keywords_en("sad, melancholic, piano") == "sad, melancholic, piano"
    assert conv.validar_keywords_en("party, danceable, upbeat") == "party, danceable, upbeat"
    # Las palabras "meta" (mood, era…) se quitan, no son señal musical
    assert conv.validar_keywords_en("mood, indie, acoustic, era, 90s") == "indie, acoustic, 90s"
    assert conv.validar_keywords_en("mood, genre, tempo") is None
    assert conv.validar_keywords_en("") is None
    print("✅ Las keywords de intención se validan (se rechaza texto en español y ruido)")


def test_tonos_coloquiales():
    clave, _, keywords = conv.detectar_tono("Hola, ando con el ánimo bajito hoy")
    assert clave == "triste", (clave, keywords)
    clave, _, keywords = conv.detectar_tono("Algo más animado, por favor")
    assert clave in ("alegre", "energia") and ("happy" in keywords or "energetic" in keywords), (clave, keywords)
    clave, _, _ = conv.detectar_tono("dame otra tanda parecida pero más tranquila")
    assert clave == "relax", clave
    print("✅ Tonos coloquiales en español (bajito, animado, tranquila)")


def test_citas_inventadas():
    canciones = [
        {"track_name": "Matilda", "artist_name": "Alt-J"},
        {"track_name": "Gimme Some Lovin'", "artist_name": "The Spencer Davis Group"},
    ]
    texto = 'Claro, "The Night" de Dua Lipa te va a encantar. Prueba «Matilda» de Alt-J.'
    limpio = conv.descartar_citas_inventadas(texto, canciones)
    assert "Dua Lipa" not in limpio, limpio
    assert "Matilda" in limpio, limpio

    vacio = conv.descartar_citas_inventadas('Escucha "The Night" de Dua Lipa.', canciones)
    reforzado = conv.garantizar_canciones(vacio, canciones)
    assert "Matilda" in reforzado or "Gimme" in reforzado, reforzado
    print("✅ Se descartan citas inventadas y se garantiza una canción real")


def test_cierre_con_pregunta():
    assert conv.cerrar_con_pregunta("Te dejo «Matilda».", 0).endswith("?")
    ya = "¿Seguimos en esa línea?"
    assert conv.cerrar_con_pregunta(ya, 0) == ya
    print("✅ Toda respuesta cierra con una pregunta")


def main() -> int:
    pruebas = [
        test_limpieza_think,
        test_402_salta_al_siguiente,
        test_429_reintenta_una_vez,
        test_todos_caidos,
        test_clasificacion_y_tono,
        test_respuesta_determinista,
        test_historial_como_turnos,
        test_validar_keywords,
        test_tonos_coloquiales,
        test_citas_inventadas,
        test_cierre_con_pregunta,
    ]
    fallos = 0
    for prueba in pruebas:
        try:
            prueba()
        except AssertionError as exc:
            fallos += 1
            print(f"❌ {prueba.__name__}: {exc}")
        except Exception as exc:  # pragma: no cover
            fallos += 1
            print(f"❌ {prueba.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{'✅' if not fallos else '❌'} {len(pruebas) - fallos}/{len(pruebas)} pruebas OK")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
