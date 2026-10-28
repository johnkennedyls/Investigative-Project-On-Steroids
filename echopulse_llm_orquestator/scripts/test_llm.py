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

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import conversacion as conv  # noqa: E402
import perfiles  # noqa: E402
import rerank  # noqa: E402
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
    # El refuerzo rota: dos turnos seguidos sin citar nada no pueden decir literalmente
    # la misma frase (en la demo delataba que era plantilla).
    r1 = conv.garantizar_canciones(vacio, canciones, turno=1)
    r2 = conv.garantizar_canciones(vacio, canciones, turno=2)
    assert r1 != reforzado and r2 != r1, (reforzado, r1, r2)
    assert all(("Matilda" in x or "Gimme" in x) for x in (r1, r2)), (r1, r2)
    print("✅ Se descartan citas inventadas y se garantiza una canción real")


def test_cierre_con_pregunta():
    assert conv.cerrar_con_pregunta("Te dejo «Matilda».", 0).endswith("?")
    ya = "¿Seguimos en esa línea?"
    assert conv.cerrar_con_pregunta(ya, 0) == ya
    print("✅ Toda respuesta cierra con una pregunta")


def test_el_refuerzo_no_contamina_el_historial():
    """Lo que inyectamos nosotros no se le muestra al modelo como si fuera suyo.

    Qwen 1.5B imita el historial: si el refuerzo de plantilla queda guardado, la
    respuesta siguiente repite la misma frase literal y toda la demo suena a robot.
    """
    canciones = [{"track_name": "matilda", "artist_name": "alt-j"}]
    salida = conv.garantizar_canciones("Hoy toca algo tranquilo.", canciones, turno=0)
    assert "Para que no se pierda" in salida, salida
    guardado = conv.sin_refuerzos_de_plantilla(salida)
    assert "Para que no se pierda" not in guardado, guardado
    assert "Hoy toca algo tranquilo." in guardado, guardado

    # Una respuesta sin refuerzo no se toca.
    natural = "Suena bien. ¿Le subimos?"
    assert conv.sin_refuerzos_de_plantilla(natural) == natural
    # Si el modelo no dijo nada propio, no queda nada que guardar (el historial
    # descarta vacíos, no se le manda un turno hueco).
    solo_refuerzo = conv.garantizar_canciones("", canciones, turno=0)
    assert conv.sin_refuerzos_de_plantilla(solo_refuerzo) == "", solo_refuerzo
    print("✅ El refuerzo de plantilla no se cuela en el historial del modelo")


def test_validar_respuesta_rechaza_basura():
    """Incidentes vistos en la demo: enumeración vacía y divagación sin canciones.

    `validar_respuesta` es la única puerta de salida del texto del modelo: si no
    queda nada aprovechable devuelve None y el orquestador usa el motor
    determinista. Nunca se devuelve el texto crudo (ese fue el bug).
    """
    canciones = [
        {"track_name": "Matilda", "artist_name": "Alt-J"},
        {"track_name": "Gimme Some Lovin'", "artist_name": "The Spencer Davis Group"},
    ]
    assert conv.validar_respuesta("1. 2. 3.", canciones, turno=0) is None
    assert conv.validar_respuesta("", canciones) is None
    assert conv.validar_respuesta("   ", canciones) is None
    # Numeración vacía: se quitan los marcadores. Si al final no queda prosa
    # útil se descarta; si queda, las canciones reales tienen que estar.
    solo_lista = conv.validar_respuesta("Claro! Aquí va: 1. 2. 3.", canciones, turno=0)
    assert solo_lista is None or ("1." not in solo_lista and "Matilda" in solo_lista), solo_lista

    buena = conv.validar_respuesta(
        'Me alegra: «Matilda» de Alt-J va justo por ahí. La segunda es «Gimme Some Lovin\'».',
        canciones, turno=1,
    )
    assert buena is not None and "Matilda" in buena, buena
    assert buena.rstrip().endswith("?"), buena
    # Nombres que no están en la lista: la frase se descarta, la respuesta se
    # reconstruye con canciones reales (no se muestra la invención).
    inventada = conv.validar_respuesta(
        'Escucha "The Night" de Dua Lipa, es perfecta para hoy y suena muy actual.',
        canciones, turno=0,
    )
    assert inventada is None or "Dua Lipa" not in inventada, inventada
    if inventada:
        assert "Matilda" in inventada or "Gimme" in inventada, inventada
    # Sin candidatos con nombre no hay nada que decir: mejor el respaldo.
    assert conv.validar_respuesta(
        "No encontré canciones con nombre en esta tanda, prueba otro mood.", [], turno=0
    ) is None
    print("✅ La salida basura del LLM se rechaza (nunca se reinyecta el texto crudo)")


def test_artista_inventado_se_corrige():
    """«okkervil river» de 'Okkervil Riffs': el título es real, el artista no."""
    canciones = [{"track_name": "Palomita", "artist_name": "Okkervil River"}]
    corregido = conv.corregir_parejas_artista(
        'Te dejo «Palomita» de Okkervil Riffs, es de su primera etapa.', canciones
    )
    assert "Okkervil Riffs" not in corregido, corregido
    assert "Okkervil River," in corregido or "Okkervil River " in corregido, corregido
    # Un artista que ya es correcto no se toca (ni se duplica ni se rompe).
    intacto = 'Suena bien: «Palomita» de Okkervil River.'
    assert conv.corregir_parejas_artista(intacto, canciones) == intacto
    # Título desconocido: se deja, lo descarta el paso siguiente de la cadena.
    otro = 'Prueba «Temaza» de Alguien Inventado.'
    assert conv.corregir_parejas_artista(otro, canciones) == otro
    assert conv.validar_respuesta(otro, canciones, turno=0) is None
    print("✅ El artista mal emparejado se corrige con el del catálogo")


def test_perfil_de_animo():
    """El retrieval ahora mira género y ánimo: era lo que faltaba para 'tranquilo'."""
    generos, animo = perfiles.perfil_consulta("calm relaxing")
    assert generos == set(), generos
    assert animo["energy_lyr"] < 0.35 and animo["loud_lyr"] < 0.35, animo

    generos, animo = perfiles.perfil_consulta("rock guitar")
    assert generos == {"rock"}, generos

    generos, animo = perfiles.perfil_consulta("party danceable upbeat")
    assert animo["dance_lyr"] > 0.7 and animo["energy_lyr"] > 0.7, animo

    # "hip hop" llega como dos términos y ambos apuntan al mismo género del catálogo
    assert perfiles.perfil_consulta("hip hop")[0] == {"hip hop"}
    # metal/punk/grunge se mapean a 'rock', que es lo que existe en la tabla maestra
    assert perfiles.perfil_consulta("heavy metal")[0] == {"rock"}
    # una consulta sin señal no debe inventar un perfil (no se castiga a nadie)
    assert perfiles.perfil_consulta("mood, genre, tempo") == (set(), {})
    assert perfiles.perfil_consulta("") == (set(), {})
    print("✅ Perfil de género/ánimo por keywords EN")


def test_perfil_vector():
    """Una fila tranquila puntúa más que una energética para 'calm relaxing'."""
    filas_gen = [{"rock"}, {"pop"}]
    cuantiles = np.array(
        [[0.90, 0.80, 0.50, 0.10, 0.10, 0.90],   # rock, alta energía y volumen
         [0.15, 0.20, 0.60, 0.20, 0.20, 0.20]],  # suave
        dtype=np.float32,
    )
    generos, animo = perfiles.perfil_consulta("calm relaxing")
    v = perfiles.perfil_vector(generos, animo, filas_gen, list(perfiles.FEATURES), cuantiles)
    assert v is not None and v[1] > v[0], v

    # Con género pedido, la fila del género correcto manda
    v2 = perfiles.perfil_vector({"rock"}, {}, filas_gen, list(perfiles.FEATURES), cuantiles)
    assert v2[0] > v2[1], v2

    # Sin señal de consulta no hay componente que ponderar
    assert perfiles.perfil_vector(set(), {}, filas_gen, list(perfiles.FEATURES), cuantiles) is None
    # Rasgos ausentes del catálogo se ignoran, no se fuerzan a 0
    v3 = perfiles.perfil_vector(set(), animo, filas_gen, [], None)
    assert v3 is None or len(v3) == len(filas_gen)
    print("✅ Vector de perfil: el mood pedido ordena el catálogo")


def test_generos_canonicos():
    """Las etiquetas del catálogo se leen como géneros, no como tokens sueltos.

    `album_genre` viene como texto libre ("Rock and Roll", "Rhythm & Blues"):
    tokenizar en crudo daba 'and', 'music', 'roll' y además rompía "hip hop"
    en dos tokens que nunca coincidían con la consulta.
    """
    assert perfiles.canonicos("Rock and Roll") == {"rock"}
    assert perfiles.canonicos("rhythm & blues") == {"blues"}
    assert perfiles.canonicos("Hip Hop, rap comercial") == {"hip hop", "pop"}
    assert perfiles.canonicos("unknown") == set()
    assert perfiles.canonicos("") == set()
    assert perfiles.canonicos(None) == set()
    # El cruce consulta/fila ahora sí funciona para "hip hop"
    generos, _ = perfiles.perfil_consulta("hip hop rap")
    assert generos == {"hip hop"}, generos
    d = perfiles.desvio_genero(generos, [{"hip hop"}, {"jazz"}])
    assert d.tolist() == [0.0, 1.0], d
    assert perfiles.desvio_genero(set(), [{"rock"}]) is None
    print("✅ Etiquetas de género canónicas (y 'hip hop' deja de partirse)")


def test_desvio_animo_castiga_lo_opuesto():
    """El guardabarros de ánimo: lo pedido explícitamente multiplica, no vota.

    Con peso 0.35 dentro del blend, una canción de energía opuesta aún colaba
    por similitud neural. El desvío se aplica como factor (1 - FILTRO*desvío),
    así que el filtro no depende de cuánta señal aporten las otras señales.
    """
    cuantiles = np.array(
        [[0.90, 0.80, 0.50, 0.10, 0.10, 0.90],   # alta energía y volumen
         [0.15, 0.20, 0.60, 0.20, 0.20, 0.20]],  # suave
        dtype=np.float32,
    )
    nombres = list(perfiles.FEATURES)
    _, animo = perfiles.perfil_consulta("calm relaxing")
    assert animo, "calm relaxing debe pedir rasgos de ánimo"

    d = perfiles.distancia_animo(animo, nombres, cuantiles)
    assert d is not None and d[0] > d[1], d
    assert d.min() >= 0 and d.max() <= 1, d

    filtro = 0.60
    factor = 1 - filtro * d
    assert factor[0] < factor[1], factor
    assert factor[1] > 0.9, factor          # la fila en la banda pedida casi no se castiga

    # Sin pedido explícito de ánimo no existe castigo: una consulta neutra
    # no puede penalizar a todo el catálogo por igual.
    assert perfiles.distancia_animo({}, nombres, cuantiles) is None
    assert perfiles.distancia_animo({"energy_lyr": 0.2}, [], cuantiles) is None
    assert perfiles.distancia_animo({"energy_lyr": 0.2}, nombres, None) is None
    print("✅ Guardabarros de ánimo: castigo multiplicativo al pedido explícito")


def test_perfil_se_hereda_en_continuacion():
    """"dame más de esa energía" cambia el ánimo pero sigue pidiendo el género previo.

    Sin herencia el turno de continuación llega sin género y el cupo de
    emergentes (7/10) rellena la tanda de jazz/blues aunque la charla iba de rock.
    """
    generos, animo = perfiles.perfil_consulta("more energetic")
    assert animo and not generos, (generos, animo)

    g2, a2, heredado = perfiles.heredar_perfil(
        generos, animo, (["rock"], {"energy_lyr": 0.2, "loud_lyr": 0.2})
    )
    assert g2 == {"rock"} and heredado, (g2, heredado)
    # El ánimo que el usuario acaba de pedir manda: no se mezcla con el heredado.
    assert a2 == animo, a2

    # Turno sin ninguna señal nueva: se arrastra el perfil previo completo.
    g3, a3, h3 = perfiles.heredar_perfil(set(), {}, (["rock"], {"energy_lyr": 0.2}))
    assert (g3, a3, h3) == ({"rock"}, {"energy_lyr": 0.2}, True), (g3, a3, h3)

    # Un género explícito en este turno no se pisa con el anterior.
    g4, _, h4 = perfiles.heredar_perfil({"jazz"}, {}, (["rock"], {}))
    assert g4 == {"jazz"} and not h4, (g4, h4)

    # Sin herencia (primer turno o petición nueva) el perfil no cambia.
    assert perfiles.heredar_perfil(generos, animo, None) == (generos, animo, False)
    print("✅ Turno de continuación: el género anterior se hereda si no se nombra otro")


def test_rerank_cobertura_y_neutro():
    """M3 no conoce todo el pool de M2: la desconocida ya no se hunde con 0.

    Cobertura explícita: si el re-ranker no aporta nada, la tesis tiene que
    poder decirlo en vez de mostrar 10 intents en 0.0000 sin explicación.
    """
    cands = [{"id": f"s{i}", "similarity": round(0.90 - i * 0.05, 4)} for i in range(4)]
    scored, diag = rerank.fusionar(cands, {"s0": 0.02, "s2": 0.01})
    assert diag["cobertura_m3"] == 0.5, diag
    assert diag["intent_neutra"] == 0.75, diag  # mediana de {1.0, 0.5}
    assert scored[0]["id"] == "s0" and scored[0]["intent_conocida"] is True
    for c in scored:
        if not c["intent_conocida"]:
            assert c["intent_score"] == diag["intent_neutra"], c
    # Pool completo fuera de las clases de M3: se conserva el orden de M2
    scored2, diag2 = rerank.fusionar(cands, {})
    assert diag2["cobertura_m3"] == 0 and diag2["m3_aporto_orden"] is False, diag2
    assert [c["id"] for c in scored2] == [c["id"] for c in cands], scored2
    assert scored2[0]["intent_score"] == 0.0
    assert rerank.fusionar([], {})[1]["cobertura_m3"] == 0.0
    print("✅ Fusión M2/M3 con cobertura medida y penalización neutra")


def test_cita_a_medias_se_suelta():
    """Recortar frases no puede dejar «…podrías probar "Dear Mr» colgado.

    Paso visto en la demo real: Qwen enumeraba bien y el corte por frases lo
    dejaba con una comilla sin cerrar, que se leía como fallo del agente.
    """
    candidatos = [
        {"track_name": "green onions", "artist_name": "booker t  the mgs"},
        {"track_name": "dear mr fantasy", "artist_name": "traffic"},
    ]
    texto = (
        '¡Por supuesto! Si buscas rock con garra, recomiendo "Green Onions" de '
        'booker t the mgs. Es una clásica. Además, podrías probar "Dear Mr'
    )
    salida = conv.validar_respuesta(texto, candidatos)
    assert salida is not None, "la parte citada y balanceada sí es aprovechable"
    assert '"Dear Mr' not in salida, salida
    assert "Green Onions" in salida or "green onions" in salida.lower(), salida
    assert salida.count('"') % 2 == 0, salida
    assert salida.rstrip().endswith("?"), salida
    # El apóstrofo de un nombre real no es una comilla sin cerrar
    ok = conv.soltar_comillas_colgadas("Suena Booker T. & the M.G.'s, un clásico.")
    assert ok == "Suena Booker T. & the M.G.'s, un clásico.", ok
    print("✅ Citas cortadas a medias se sueltan sin romper los apóstrofos")


def test_metricas_ranking():
    """HR/Recall/Precision/MRR/NDCG sobre etiquetas sintéticas, con valor a mano.

    La tesis no puede sacar estas métricas de los contadores de operación:
    se calculan cruzando logs/events_*.jsonl con logs/feedback_*.jsonl.
    """
    import importlib.util

    ruta = RAIZ / "scripts" / "evaluar_metricas.py"
    espec = importlib.util.spec_from_file_location("evaluar_metricas", ruta)
    em = importlib.util.module_from_spec(espec)
    espec.loader.exec_module(em)

    ranking = [
        {"rank": i, "track_name": f"cancion {i}", "artist_name": f"artista {i}",
         "generos": ["rock"] if i % 2 == 0 else ["rock", "blues"]}
        for i in range(1, 11)
    ]
    eventos = {
        "e1": {"id": "e1", "ranking": [dict(c) for c in ranking],
               "calidad": {"cobertura_m3": 0.2, "tipo_turno": "musica"},
               "latencies_ms": {"total": 100}},
        "e2": {"id": "e2", "ranking": [dict(c) for c in ranking],
               "calidad": {"tipo_turno": "mas_de_lo_mismo", "perfil_heredado": True},
               "latencies_ms": {"total": 200}},
        "e3": {"id": "e3", "ranking": [dict(c) for c in ranking], "calidad": {}, "latencies_ms": {"total": 300}},
    }
    etiquetas = [
        {"evento_id": "e1", "valor": "gust", "track_name": "Canción 3"},
        {"evento_id": "e2", "valor": "no_gust", "track_name": "cancion 1"},
        {"evento_id": "e3", "valor": "gust", "track_name": "no existe en el turno"},
        {"evento_id": "fantasma", "valor": "gust", "track_name": "cancion 1"},
    ]

    e = em.metricas_etiquetados(eventos, etiquetas, estricto=True)
    assert e["turnos_etiquetados"] == 3, e           # la etiqueta huérfana no cuenta
    assert e["hit_rate@1"] == 0.0, e                 # la aceptada estaba en el puesto 3
    assert e["hit_rate@5"] == round(1 / 3, 4), e
    assert e["precision@5"] == round(0.2 / 3, 4), e  # 1 acierto en 5 slots, 3 turnos
    assert e["recall@5"] == 1.0, e                   # la única relevante sí entró
    assert e["mrr"] == round((1 / 3) / 3, 4), e
    assert e["ndcg@5"] == round((1 / np.log2(4)) / 3, 4), e
    assert e["posicion_media_de_acierto"] == 3.0, e
    assert e["gust_sin_cancion_en_el_ranking"] == 1, e
    assert e["etiquetas_sin_evento"] == 1, e

    a = em.metricas_etiquetados(eventos, etiquetas, estricto=False)
    # Amplio: los 2 turnos "gust" cuentan las 10 canciones como relevantes, así que
    # todo entra en el top 1 y HR=MRR=NDCG=2/3; Recall@1 solo 0.1 (1 de 10).
    assert a["hit_rate@1"] == round(2 / 3, 4), a
    assert a["recall@1"] == 0.1, a
    assert a["ndcg@10"] == round(2 / 3, 4), a
    assert a["gust_sin_cancion_en_el_ranking"] == 0, a

    t = em.telemetria(eventos)
    assert t["turnos_registrados"] == 3, t
    # Géneros canónicos de la ficha (multi-etiqueta), no la columna cruda `genre`.
    assert t["generos_entregados"] == {"rock": 30, "blues": 15}, t
    assert t["turnos_de_continuacion"] == {"musica": 1, "mas_de_lo_mismo": 1, "?": 1}, t
    assert t["turnos_con_perfil_heredado"] == 1, t

    # Alineación: proxy del retrieval que no necesita etiquetas.
    for c in eventos["e1"]["ranking"]:
        c["cumple_genero"] = c["rank"] <= 7          # 7 de 10 dentro del género pedido
        c["desvio_animo"] = 0.1 * c["rank"]
    al = em.alineacion(eventos)
    assert al["turnos_con_genero_pedido"] == 1, al
    assert al["coherencia_de_genero"] == 0.7, al
    assert al["coherencia_de_genero_top3"] == 1.0, al
    assert al["desvio_de_animo_promedio"] == round(sum(range(1, 11)) / 10 * 0.1, 4), al

    # Turnos sin pedido explícito no aportan a la métrica (no hay con qué comparar)
    assert em.alineacion({"x": {"ranking": [{"rank": 1}]}})["coherencia_de_genero"] is None

    # Sin etiquetas no hay métricas de ranking, por muchas consultas que existan.
    assert em.metricas_etiquetados(eventos, [], estricto=True) is None
    print("✅ Métricas de ranking y alineación calculadas sobre etiquetas")


def test_el_limite_por_ip_frena_el_spam():
    """Ventana deslizante: entran `limite` turnos, el siguiente no, y luego vuelve.

    La demo pública se expone en HTTP directo, así que este freno es lo único
    que protege los 2 núcleos de la VM de una cola infinita de turnos.
    """
    import limite

    lim = limite.LimitadorVentana(limite=3, ventana=60.0)
    t0 = 1000.0
    assert [lim.permitir("1.2.3.4", t0 + i) for i in range(3)] == [True, True, True]
    assert lim.permitir("1.2.3.4", t0 + 3) is False
    # Los rechazos no se suman como golpes: la ráfaga caduca, no se renueva sola.
    assert lim.permitir("1.2.3.4", t0 + 4) is False
    # Otra IP no paga el exceso de la primera.
    assert lim.permitir("5.6.7.8", t0 + 4) is True
    # Ventana deslizante: caduca el golpe más viejo, no el reloj entero.
    assert lim.permitir("1.2.3.4", t0 + 61) is True

    sin_freno = limite.LimitadorVentana(limite=0)
    assert all(sin_freno.permitir("localhost") for _ in range(500))
    print("✅ Límite por IP: ventana deslizante de 3/min con la cola protegida")


def test_la_cabecera_xff_solo_vale_detras_del_proxy():
    """Con el túnel ngrok el origen real viene en X-Forwarded-For, no en la conexión.

    Sin leer esa cabecera todos los visitantes caerían en el mismo cubo del límite
    (y 12 turnos/min se quedarían cortísimos). Pero la cabecera solo se cree si
    quien llama es una IP privada: si no, cualquiera la inventa para saltárselo.
    """
    import limite

    detras_del_proxy = limite.ip_cliente("172.18.0.5", "8.8.8.8, 172.18.0.5")
    assert detras_del_proxy == "8.8.8.8", detras_del_proxy
    # HTTP directo (puerto 80 abierto): manda la conexión, la cabecera es ruido.
    directo = limite.ip_cliente("8.8.8.8", "1.1.1.1")
    assert directo == "8.8.8.8", directo
    assert limite.ip_cliente("172.18.0.5", None) == "172.18.0.5"
    assert limite.ip_cliente(None, "8.8.8.8") == "desconocida"

    # Cada visitante real ocupa su propio cubo; el que repite, frena.
    lim = limite.LimitadorVentana(limite=1, ventana=60.0)
    t0 = 500.0
    assert lim.permitir(limite.ip_cliente("172.18.0.5", "8.8.8.8"), t0)
    assert lim.permitir(limite.ip_cliente("172.18.0.5", "1.1.1.1"), t0)
    assert not lim.permitir(limite.ip_cliente("172.18.0.5", "8.8.8.8"), t0 + 1)
    print("✅ IP del visitante: X-Forwarded-For solo detrás del proxy")


def test_la_voz_no_puede_citar_fuera_de_las_tarjetas():
    """Lo que Qwen nombra tiene que estar entre las canciones que se ven.

    Incidente real: la voz decía "Shes Always Singing — The Dear Hunter" y
    "Still Im Sad — The Yardbirds" cuando las tarjetas mostraban otras tres. El
    orquestador ahora da a validar solo las `destacadas` (las mismas que corta el
    frontend), así que una cita de más abajo del ranking se cae frase a frase.
    """
    import conversacion

    tarjetas = [
        {"track_name": "say yeah", "artist_name": "wiz khalifa"},
        {"track_name": "my time", "artist_name": "fabolous"},
        {"track_name": "pusha man", "artist_name": "chance the rapper"},
    ]
    mas_abajo = {"track_name": "blackout", "artist_name": "breathe carolina"}
    cita_inventada = 'Te dejo «say yeah» de wiz khalifa. También suena «blackout».'

    con_tarjetas = conversacion.descartar_citas_inventadas(cita_inventada, tarjetas)
    assert "blackout" not in con_tarjetas.lower(), con_tarjetas
    assert "say yeah" in con_tarjetas.lower(), con_tarjetas

    # Con la lista larga del prompt viejo la misma cita pasaba: recortar a las
    # destacadas es lo que cierra la puerta.
    con_lista_larga = conversacion.descartar_citas_inventadas(
        cita_inventada, tarjetas + [mas_abajo]
    )
    assert "blackout" in con_lista_larga.lower(), con_lista_larga
    print("✅ La voz cita solo las tarjetas: nada de más abajo del ranking")


def test_el_eco_del_prompt_se_traduce_a_lenguaje_hablado():
    """El volcado de la lista interna tiene que sonar a frase, no a datos.

    Pasillo real: Qwen devolvió `"Add Some Music to Your Day" — The Beach Boys [Pop]`
    y las tarjetas mostraban esas mismas canciones. Borrar el eco dejaba una frase
    huérfana ("te recomiendo: Es una canción suave…"), así que se traduce al formato
    hablado que el prompt pide. Además una fila sin nombre real no puede ser
    recomendación.
    """
    import conversacion

    eco = (
        '"Add Some Music to Your Day" — The Beach Boys [Pop] "i love you" — '
        "Sarah Mclachlan [Pop] Espero que te ayude a concentrarte."
    )
    limpio = conversacion.limpiar_ecos_de_lista(eco)
    assert "—" not in limpio, limpio
    assert '"' not in limpio, limpio
    assert "[Pop]" not in limpio and "[pop]" not in limpio.lower(), limpio
    assert limpio.count("«") == 2, limpio
    assert "de The Beach Boys" in limpio and "de Sarah Mclachlan" in limpio, limpio
    assert "concentrarte" in limpio, limpio

    legitima = "Te dejo «say yeah» de wiz khalifa. ¿Seguimos?"
    assert conversacion.limpiar_ecos_de_lista(legitima) == legitima, legitima

    mixta = [
        {"track_name": "unknown", "artist_name": "the beach boys"},
        {"track_name": "i love you", "artist_name": "sarah mclachlan"},
    ]
    reales = conversacion.canciones_reales(mixta)
    assert [c["track_name"] for c in reales] == ["i love you"], reales
    assert conversacion.canciones_reales([mixta[0]]), "nunca puede quedar vacía"
    print("✅ El eco del prompt se habla en natural y las filas sin nombre se descartan")


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
        test_el_refuerzo_no_contamina_el_historial,
        test_validar_respuesta_rechaza_basura,
        test_artista_inventado_se_corrige,
        test_cita_a_medias_se_suelta,
        test_perfil_de_animo,
        test_perfil_vector,
        test_generos_canonicos,
        test_desvio_animo_castiga_lo_opuesto,
        test_perfil_se_hereda_en_continuacion,
        test_rerank_cobertura_y_neutro,
        test_metricas_ranking,
        test_el_limite_por_ip_frena_el_spam,
        test_la_cabecera_xff_solo_vale_detras_del_proxy,
        test_la_voz_no_puede_citar_fuera_de_las_tarjetas,
        test_el_eco_del_prompt_se_traduce_a_lenguaje_hablado,
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
