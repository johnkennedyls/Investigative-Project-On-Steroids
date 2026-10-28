# conversacion.py - Prompts y motor conversacional de EchoPulse
"""
Dos piezas separadas para que el agente converse incluso sin LLM:

1. PROMPTS: cómo se le pide a Qwen (a) las keywords de intención y (b) la
   respuesta hablada. El historial se envía como TURNOS reales de chat
   (`messages`), no como un texto aplanado: así el modelo recuerda, retoma
   canciones previas y responde como en una conversación.

2. MOTOR DETERMINISTA: respuesta conversacional sin red ni modelo, para que la
   demo nunca se quede muda (HF sin créditos, Ollama apagado, etc.). No es una
   plantilla única: detecta el tono, reacciona a lo que dijo el usuario, cita
   canciones reales y cierra con una pregunta distinta cada turno.
"""

from __future__ import annotations

import re
from typing import Sequence

# =====================================================================
# PROMPTS
# =====================================================================
SISTEMA_INTENCION = (
    "Eres el motor de intención de EchoPulse, un recomendador musical conversacional. "
    "Recibes la conversación y el ÚLTIMO mensaje del usuario. "
    "Devuelve SOLO de 3 a 5 keywords en inglés separadas por comas, describiendo el "
    "mood, género o estilo que quiere AHORA (mood, genre, tempo, era, instrumentación). "
    "No escribas explicaciones, ni comillas, ni listas con viñetas. "
    "Si pide 'más', 'otras parecidas' o se refiere a algo anterior, conserva el vibe "
    "previo y cambia solo lo que pida. "
    "Si el mensaje no es una petición musical (saludo, pregunta, charla), devuelve "
    "igual las keywords del último vibe conocido o 'chill music' si no hay ninguno."
)

SISTEMA_CHAT = (
    "Eres un curador musical que conversa como un amigo melómano: cercano, "
    "con criterio y sin sonar a vendedor. "
    "Reglas: "
    "1) Responde SIEMPRE en español, en 2 a 4 frases, tono cálido y natural. "
    "2) Reacciona primero a lo que dijo el usuario (su mood, su pregunta) y después "
    "recomienda. "
    "3) Menciona 2 o 3 canciones de la lista entregada, con su nombre y artista "
    "exactos; nunca inventes canciones, artistas ni datos. La lista es información "
    "interna: no copies sus líneas ni su formato (nada de guiones, «» ni corchetes). "
    "4) Nunca muestres IDs, códigos, corchetes ni puntuaciones de similitud. "
    "5) No repitas canciones ya mencionadas antes en la conversación. "
    "6) Si el usuario hace una pregunta en vez de pedir música, respóndela con tu "
    "criterio y luego conecta con la lista. "
    "7) Cierra con UNA pregunta breve que invite a seguir hablando, distinta cada "
    "vez. La pregunta es sobre lo que TÚ acabas de proponer (más fuerte, más suave, "
    "otro estilo): nunca le pidas al usuario que te recomiende música a ti. "
    "8) Sin viñetas, sin numeración, sin encabezados, sin comillas alrededor de la "
    "respuesta y con un emoji como máximo. "
    "9) Trátalo de tú y no nombres a nadie: ni a ti ni a él (no sabes cómo se "
    "llama). Empieza directo con tu reacción o con la canción."
)

PREGUNTAS_SEGUIMIENTO = [
    "¿Seguimos en esa línea o le subimos un poco la energía?",
    "¿Te suena para ahora mismo o lo guardamos para otro momento?",
    "¿Quieres que tire más hacia ese artista o que te sorprenda con algo distinto?",
    "¿Prefieres algo más tranquilo o nos quedamos con este mood?",
    "¿Le damos otra vuelta con algo más de ese estilo?",
    "¿Buscamos algo parecido pero de otra época?",
]

# Refuerzo cuando el modelo no citó canciones reales. `{lista}` trae uno o dos
# pares «título» de artista, así que las frases tienen que funcionar en singular.
REFUERZOS_CANCION = [
    "Para que no se pierda, mis apuestas de esta tanda son {lista}.",
    "De lo que te traje, me mojo por {lista}.",
    "Si te quedas con algo, quédate con {lista}.",
    "Lo más directo de esta tanda: {lista}.",
]


# =====================================================================
# Utilidades de texto
# =====================================================================
def normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def _minus(texto: str) -> str:
    return normalizar(texto).lower()


def formatear_canciones(candidatos: Sequence[dict], limite: int = 3) -> str:
    """'«A» de X, «B» de Y y «C» de Z' solo con canciones que tengan nombre real."""
    piezas = []
    for candidato in candidatos:
        nombre = normalizar(candidato.get("track_name"))
        artista = normalizar(candidato.get("artist_name"))
        if not nombre or nombre.lower() in ("unknown", "none", "nan"):
            continue
        if artista and artista.lower() not in ("unknown", "none", "nan"):
            piezas.append(f"«{nombre}» de {artista}")
        else:
            piezas.append(f"«{nombre}»")
        if len(piezas) >= limite:
            break
    if not piezas:
        return ""
    if len(piezas) == 1:
        return piezas[0]
    return ", ".join(piezas[:-1]) + " y " + piezas[-1]


def clasificar_mensaje(mensaje: str) -> str:
    """Clasificación gruesa del turno, sin LLM."""
    texto = _minus(mensaje)
    if not texto:
        return "vacio"
    if re.fullmatch(r"(hola|hey|holaa+|buenas|qué tal|que tal|buenos días|buenas tardes|buenas noches)[!. ]*", texto):
        return "saludo"
    if re.search(r"\b(gracias|buenísimo|buenisimo|me encanta|me gusta|qué chevere|que chevere|excelente|perfecto)\b", texto):
        return "feedback_positivo"
    if re.search(r"\b(no me gusta|no sirve|no era|equis|malísimo|malisimo|siguiente)\b", texto):
        return "feedback_negativo"
    if re.search(r"\b(más|mas|otra|otras|otro|otros|parecid\w*|similar\w*|sigue|seguir|continúa|continua)\b", texto):
        return "mas_de_lo_mismo"
    if "?" in texto or re.match(r"^(qué|que|cómo|como|cuál|cual|por qué|porque|cuándo|cuando|dónde|donde|quién|quien|me recomiendas|preferirías|preferirias)\b", texto):
        return "pregunta"
    return "musica"


# =====================================================================
# Detección de tono (ES) sin LLM
# =====================================================================
# clave -> (etiqueta para hablar, keywords EN para el retrieval)
TONOS: dict[str, tuple[str, str]] = {
    "triste": ("más melancólico y pausado", "sad melancholic"),
    "alegre": ("alegre y de buen ánimo", "happy upbeat feel good"),
    "fiesta": ("de fiesta y con energía", "party danceable upbeat"),
    "relax": ("tranquilo y sin prisa", "calm relaxing"),
    "energia": ("con energía para moverte", "energetic motivational"),
    "amor": ("romántico", "romantic love"),
    "focus": ("para concentrarte", "instrumental focus"),
    "rock": ("rock con garra", "rock guitar"),
    "metal": ("metal pesado", "heavy metal"),
    "pop": ("pop", "pop"),
    "rap": ("rap / hip hop", "rap hip hop"),
    "jazz": ("jazz", "jazz"),
    "electronica": ("electrónica", "electronic"),
    "clasica": ("clásica / orquestal", "classical orchestral"),
    "folk": ("folk", "folk acoustic"),
    "indie": ("indie", "indie"),
    "reggae": ("reggae", "reggae"),
    "vintage": ("con sabor retro", "retro vintage"),
    "verano": ("de verano", "summer"),
    "noche": ("de noche", "night"),
    "lluvia": ("de día lluvioso", "rainy"),
}

# Tonos que son género/estilo (se pueden combinar con un estado de ánimo)
_GENEROS = {
    "rock", "metal", "pop", "rap", "jazz", "electronica", "clasica", "folk",
    "indie", "reggae",
}

_TRIGGERS: dict[str, tuple[str, ...]] = {    "triste": ("triste", "tristes", "melancol", "nostalg", "desamor", "llorar", "solo", "sola",
               "bajón", "bajon", "bajit", "depre", "desanim", "sin ánimo", "sin animo", "apagado"),
    "alegre": ("alegr", "feliz", "content", "buen rollo", "buena onda", "sonreír", "sonreir",
               "de buen humor"),
    "fiesta": ("fiest", "party", "rumba", "bail", "dance", "discoteca", "celebra", "farra",
               "parche", "salir de noche"),
    "relax": ("relaj", "tranquil", "calma", "calmado", "chill", "descansar", "paz", "pausado"),
    "energia": ("energía", "energia", "subidón", "subidon", "gym", "entrenar", "correr",
                "motivación", "motivacion", "activo", "animad", "movid",
                "con pila", "caña"),
    "amor": ("amor", "romántic", "romantic", "enamor", "pareja", "corazón", "corazon"),
    "focus": ("concentrar", "estudiar", "estudi", "trabajar", "trabajo", "focus", "instrumental"),
    "rock": ("rock", "pesado", "guitarra eléctrica", "guitarra electrica", "punk", "grunge"),
    "metal": ("metal", "heavy", "death", "thrash"),
    "pop": ("pop", "comercial", "radio"),
    "rap": ("rap", "hip hop", "hiphop", "trap", "urbano"),
    "jazz": ("jazz", "swing", "blues"),
    "electronica": ("electrónic", "electronic", "techno", "house", "edm", "synth"),
    "clasica": ("clásic", "clasic", "orquest", "piano", "sinfon"),
    "folk": ("folk", "acústic", "acustic", "trova", "campo"),
    "indie": ("indie", "alternativ"),
    "reggae": ("reggae", "ska", "dub"),
    "vintage": ("vintage", "retro", "antiguo", "viejo", "clásicos", "clasicos", "época", "epoca"),
    "verano": ("verano", "playa", "sol"),
    "noche": ("noche", "nocturn", "trasnoche"),
    "lluvia": ("lluv", "torment", "invierno"),
}


def detectar_tono(mensaje: str) -> tuple[str, str, str]:
    """Devuelve (clave, frase_es, keywords_en) según lo que pide el usuario."""
    texto = _minus(mensaje)
    encontrados: list[str] = []
    for clave, triggers in _TRIGGERS.items():
        if any(t in texto for t in triggers):
            encontrados.append(clave)

    if not encontrados:
        return "neutral", "algo que te acompañe", "chill music"

    # El primero suele ser el más específico. Se combina con un segundo tono
    # solo si no son dos estados de ánimo contradictorios ("triste" + "energía").
    clave = encontrados[0]
    frase, keywords = TONOS[clave]
    for extra in encontrados[1:]:
        if clave not in _GENEROS and extra not in _GENEROS:
            continue
        keywords = f"{keywords} {TONOS[extra][1]}"
        break
    return clave, frase, keywords


# =====================================================================
# Mensajes de chat (historial como turnos reales)
# =====================================================================
def construir_mensajes(
    sistema: str,
    historial: Sequence[dict] | None,
    mensaje_usuario: str,
    max_turnos: int = 8,
) -> list[dict]:
    """system + últimos turnos reales + turno actual (formato OpenAI)."""
    mensajes: list[dict] = [{"role": "system", "content": sistema}]
    if historial:
        for turno in list(historial)[-max_turnos:]:
            rol = turno.get("role")
            contenido = normalizar(turno.get("content"))
            if rol in ("user", "assistant") and contenido:
                mensajes.append({"role": rol, "content": contenido})
    mensajes.append({"role": "user", "content": mensaje_usuario})
    return mensajes


# =====================================================================
# Motor determinista (sin LLM)
# =====================================================================
def _elegir(opciones: Sequence[str], turno: int) -> str:
    return opciones[turno % len(opciones)] if opciones else ""


def respuesta_determinista(
    mensaje: str,
    candidatos: Sequence[dict],
    sesion: dict | None = None,
) -> str:
    """Respuesta conversacional de respaldo: contextual, variada y honesta."""
    sesion = sesion or {}
    turno = int(sesion.get("turnos", 0))
    tipo = clasificar_mensaje(mensaje)
    clave_tono, frase_tono, _ = detectar_tono(mensaje)
    canciones = formatear_canciones(candidatos, limite=3)
    pregunta = _elegir(PREGUNTAS_SEGUIMIENTO, turno)
    anteriores = sesion.get("ultimos_nombres") or []
    referencia_previa = ""
    if anteriores:
        referencia_previa = f"Como veníamos con «{anteriores[0]}», "

    if tipo == "saludo":
        return (
            "¡Hola! Aquí ando, listo para armarte una selección a tu medida. "
            f"Cuéntame el mood o la situación y te propongo algo. {pregunta}"
        )

    if tipo == "feedback_positivo":
        base = f"Me alegra que te suene bien. {referencia_previa}"
        if canciones:
            return (
                f"{base}Para mantener esa línea te dejo {canciones}. "
                f"{pregunta}"
            )
        return f"{base}¿Quieres que siga con ese estilo o cambiamos de aire?"

    if tipo == "feedback_negativo":
        return (
            "Entendido, eso no era. Dame una pista: ¿más rápido, más tranquilo "
            f"o de otra época? {pregunta}"
        )

    if tipo == "pregunta":
        if canciones:
            return (
                f"Buena pregunta. Si el artista es nuevo para ti, yo arrancaría por "
                f"{canciones}: es una forma de entrar sin perderme en el catálogo. "
                f"{pregunta}"
            )
        return (
            "Buena pregunta. Yo iría por nombres que no hayas escuchado antes y "
            f"que compartan el mood que buscas. {pregunta}"
        )

    if tipo == "mas_de_lo_mismo":
        base = referencia_previa or "Sigo por esa línea: "
        if canciones:
            return (
                f"{base}te propongo {canciones}, en la misma onda pero sin repetir. "
                f"{pregunta}"
            )
        return f"{base}¿te sirve si busco algo más de ese estilo?"

    if tipo == "vacio":
        return (
            "No te escuché bien. Dime un mood, un género o una situación "
            f"(por ejemplo: 'algo para el tráfico') y te armo la lista. {pregunta}"
        )

    # Petición musical normal
    aperturas = [
        "Perfecto, vamos con eso.",
        f"Suena a que necesitas algo {frase_tono}.",
        f"Vale, me voy por lo {frase_tono}.",
        f"Entendido: {frase_tono}.",
    ]
    apertura = _elegir(aperturas, turno)
    if canciones:
        return (
            f"{apertura} Te propongo {canciones}. "
            f"Si quieres, ajusto el tono en el siguiente turno. {pregunta}"
        )
    return (
        f"{apertura} No encontré canciones con nombre para mostrarte en este momento, "
        f"pero puedo intentar con otro mood. {pregunta}"
    )


def resumen_para_memoria(mensaje: str) -> str:
    """Etiqueta corta del turno para que el motor recuerde el tono previo."""
    clave, frase, _ = detectar_tono(mensaje)
    if clave == "neutral":
        return ""
    return frase


# =====================================================================
# Control de calidad de la respuesta del LLM
# =====================================================================
_RE_CORTE_FRASE = re.compile(r"(?<=[.!?…])\s+")
# El modelo copia a veces una línea de la lista del prompt:
#   "- «we cant stop» — miley cyrus [pop]"
# Se elimina para que la respuesta no parezca un volcado de datos.
_RE_ECO_LISTA = re.compile(r"[-•]\s*«[^»]{1,150}»\s*[—–-]\s*[^¿?¡!\n]*", re.M)


def recortar_frases(texto: str, maximo: int = 5) -> str:
    """Los modelos pequeños se van de largo: dejar como mucho `maximo` frases."""
    texto = normalizar(texto)
    if not texto:
        return texto
    frases = _RE_CORTE_FRASE.split(texto)
    if len(frases) <= maximo:
        return texto
    return " ".join(frases[:maximo]).strip()


def limpiar_ecos_de_lista(texto: str) -> str:
    """Quita las líneas de la lista interna que el modelo copia literalmente."""
    limpio = _RE_ECO_LISTA.sub(" ", texto or "")
    return normalizar(limpio)


# Marcadores de lista suelta: "1." "2)" "-" "•". El prompt prohíbe las viñetas
# pero Qwen 1.5B las escribe igual, a veces SIN contenido detrás ("1. 2. 3.").
_RE_MARCADOR_VACIO = re.compile(r"(?:^|\s)(?:\d{1,2}[\).\:]|[-•*])\s*(?=\s|$)")
_RE_MARCADOR = re.compile(r"(?:^|\s)(?:\d{1,2}[\).\:]|[-•*])\s+")


def limpiar_numeraciones(texto: str) -> str:
    """Elimina las viñetas/numeración que el modelo ignora en el prompt.

    Primero borra los marcadores vacíos (el caso visto en producción: una
    respuesta que solo decía "1. 2. 3." y la tarjeta quedaba vacía); después
    aplana los que sí traen texto, conservando el contenido.
    """
    limpio = _RE_MARCADOR_VACIO.sub(" ", texto or "")
    limpio = _RE_MARCADOR.sub(" ", limpio)
    return normalizar(limpio)


def _plano(texto: str) -> str:
    """Minúsculas y sin puntuación, para comparar títulos dentro de una frase."""
    return re.sub(r"[^a-z0-9áéíóúüñ ]", " ", str(texto).lower())


def canciones_citadas(respuesta: str, candidatos: Sequence[dict]) -> list[str]:
    """Títulos de la lista que aparecen literalmente en la respuesta."""
    plano = _plano(respuesta)
    citadas = []
    for candidato in candidatos:
        titulo = normalizar(candidato.get("track_name"))
        if not titulo or titulo.lower() in ("unknown", "none", "nan"):
            continue
        if len(titulo) < 3:
            continue
        if _plano(titulo).strip() in plano:
            citadas.append(titulo)
    return citadas


def garantizar_canciones(
    respuesta: str, candidatos: Sequence[dict], maximo_frases: int = 5, turno: int = 0
) -> str:
    """Si el modelo no citó ninguna canción real, se añade la lista al final.

    Los modelos pequeños (0.5B-1.5B) a veces divagan o inventan títulos. Esto
    mantiene su tono conversacional pero asegura que el usuario reciba
    recomendaciones que existen en el catálogo. Si la respuesta termina en
    pregunta, la lista se inserta antes para que la pregunta siga cerrando.

    El refuerzo rota por turno: en una tanda de "dame más" el modelo suele no
    citar nada dos veces seguidas, y la misma frase literal delataba al plantel.
    """
    respuesta = limpiar_ecos_de_lista(respuesta)
    respuesta = recortar_frases(respuesta, maximo_frases)
    if canciones_citadas(respuesta, candidatos):
        return respuesta
    lista = formatear_canciones(candidatos, limite=2)
    if not lista:
        return respuesta
    refuerzo = _elegir(REFUERZOS_CANCION, turno).format(lista=lista)

    frases = _RE_CORTE_FRASE.split(respuesta)
    if frases and frases[-1].rstrip().endswith("?"):
        frases.insert(len(frases) - 1, refuerzo)
        return " ".join(frases).strip()
    return f"{respuesta} {refuerzo}".strip()


def sin_refuerzos_de_plantilla(texto: str) -> str:
    """Quita del historial las frases que inyectamos nosotros, no el modelo.

    El historial se reenvía al LLM en cada turno: si guardamos el refuerzo que
    añadimos porque el modelo no citó ninguna canción, Qwen 1.5B lo imita tal
    cual turno tras turno y toda la demo repite la misma frase literal.
    """
    if not texto:
        return texto
    prefijos = [frase.split("{lista}")[0].strip() for frase in REFUERZOS_CANCION]
    frases = _RE_CORTE_FRASE.split(normalizar(texto))
    guardadas = [f for f in frases if not any(f.strip().startswith(p) for p in prefijos)]
    return " ".join(guardadas).strip()


def cerrar_con_pregunta(texto: str, turno: int = 0) -> str:
    """Asegura que la respuesta invite a seguir hablando (los modelos pequeños lo olvidan)."""
    texto = normalizar(texto)
    if not texto:
        return texto
    ultima_frase = _RE_CORTE_FRASE.split(texto)[-1].rstrip()
    if ultima_frase.endswith("?"):
        return texto
    return f"{texto} {_elegir(PREGUNTAS_SEGUIMIENTO, turno)}".strip()


_RE_CITA = re.compile(r"[«\"“”']([^«»\"“”']{3,80})[»\"“”']")


def descartar_citas_inventadas(texto: str, candidatos: Sequence[dict]) -> str:
    """Quita frases que citan entre comillas un título que no existe en la lista.

    Un 1.5B en CPU inventa canciones ("The Night de Dua Lipa"). Como el catálogo
    manda, si la cita no está entre los candidatos se descarta esa frase.
    """
    validos = {
        _plano(c.get("track_name")).strip()
        for c in candidatos
        if c.get("track_name") and str(c["track_name"]).lower() not in ("unknown", "none", "nan")
    }
    if not validos:
        return texto
    conservadas: list[str] = []
    for frase in _RE_CORTE_FRASE.split(normalizar(texto)):
        citas = _RE_CITA.findall(frase)
        # `any` bastaba mientras el prompt y la validación veían los mismos 10
        # títulos; ahora la tanda son las tarjetas y una frase mezclada ("«say
        # yeah» y «blackout»") tiene una cita buena y una que no se muestra, así
        # que se descarta solo si TODAS las citas de la frase son de la lista.
        if citas and all(_plano(cita).strip() in validos for cita in citas):
            conservadas.append(frase)
    return " ".join(conservadas).strip()


# «Título» de Artista  /  "Título" by Artist  /  «Título» del Artista
# El par de comillas se agrupa por alternancia (no con \1): « abre y » cierra.
_RE_CITA_ARTISTA = re.compile(
    r"(?:«([^«»]{3,80})»|[\"“”']([^\"“”']{3,80})[\"“”'])"
    r"\s+(de|del|by|from)\s+"
    r"([^\s«»\"“”'.,;:!?][^«»\"“”'.,;:!?]{0,38})"
)


def corregir_parejas_artista(texto: str, candidatos: Sequence[dict]) -> str:
    """Reemplaza el artista mal emparejado por el real de esa canción.

    Incidente en producción: «okkervil river» de **Okkervil Riffs** — el título
    sí venía de la lista, el artista se lo inventó el modelo. Como el catálogo
    manda, la pareja (título, artista) se corrige en vez de borrar la frase, que
    es lo que el usuario estaba leyendo bien.
    """
    art_por_titulo: dict[str, str] = {}  # plano(título) -> artista real
    for c in candidatos:
        titulo = normalizar(c.get("track_name"))
        if not titulo or titulo.lower() in ("unknown", "none", "nan"):
            continue
        artista = normalizar(c.get("artist_name"))
        if artista and artista.lower() not in ("unknown", "none", "nan"):
            art_por_titulo.setdefault(_plano(titulo).strip(), artista)
    if not art_por_titulo:
        return texto

    def _corregir(m: re.Match) -> str:
        titulo = (m.group(1) or m.group(2)).strip()
        conector, artista = m.group(3), m.group(4)
        real = art_por_titulo.get(_plano(titulo).strip())
        if not real:
            return m.group(0)
        plano_capturado, plano_real = _plano(artista).strip(), _plano(real).strip()
        if (
            plano_capturado == plano_real
            or plano_real in plano_capturado
            or plano_capturado in plano_real
        ):
            return m.group(0)
        return f"«{titulo}» {conector} {real}"

    return _RE_CITA_ARTISTA.sub(_corregir, texto or "")


def texto_aprovechable(texto: str, candidatos: Sequence[dict]) -> bool:
    """¿Aporta algo la salida del modelo tras la limpieza?

    Si no, el orquestador usa el motor determinista: es mejor una respuesta
    sobria y correcta que devolver el texto crudo (que puede estar vacío,
    ser solo numeración o divagación).
    """
    if not texto or len(texto) < 25:
        return False
    if not re.search(r"[A-Za-zÁÉÍÓÚÜÜÑáéíóúüñ]{3}", texto):
        return False
    if not canciones_citadas(texto, candidatos) and not formatear_canciones(candidatos, limite=1):
        return False
    return True


def soltar_comillas_colgadas(texto: str) -> str:
    """Tira la última frase si dejó una cita sin cerrar.

    Al recortar por número de frases el modelo se queda a medias
    («…podrías probar "Dear Mr»). Una cita abierta sin cierre se lee como un
    fallo del agente, así que es mejor perder esa frase que mostrarla.
    """
    frases = _RE_CORTE_FRASE.split(normalizar(texto))
    while frases and not _citas_balanceadas(frases[-1]):
        frases.pop()
    return " ".join(frases).strip()


def _citas_balanceadas(frase: str) -> bool:
    # Los apóstrofes no se cuentan: "Booker T. & the M.G.'s" tiene uno suelto y
    # es una frase perfectamente cerrada.
    return (
        len(re.findall(r"[«“]", frase)) == len(re.findall(r"[»”]", frase))
        and frase.count('"') % 2 == 0
    )


def validar_respuesta(
    texto: str, candidatos: Sequence[dict], turno: int = 0, maximo_frases: int = 5
) -> str | None:
    """Cadena única de control de calidad sobre la salida del LLM.

    Corrección de parejas → descarte de citas por fuera de la tanda → limpieza de ecos
    de la lista interna → eliminación de numeración → recorte de frases → soltar
    citas a medias → garantía de canción real → pregunta de cierre. Devuelve `None`
    cuando no queda nada aprovechable: el llamador decide el respaldo, y en ningún
    caso se reintroduce el texto crudo del modelo.
    """
    limpio = corregir_parejas_artista(texto, candidatos)
    limpio = descartar_citas_inventadas(limpio, candidatos)
    limpio = limpiar_ecos_de_lista(limpio)
    limpio = limpiar_numeraciones(limpio)
    limpio = recortar_frases(limpio, maximo_frases)
    limpio = soltar_comillas_colgadas(limpio)
    if not texto_aprovechable(limpio, candidatos):
        return None
    garantizada = garantizar_canciones(limpio, candidatos, maximo_frases, turno)
    return cerrar_con_pregunta(garantizada, turno)


# =====================================================================
# Validación de keywords de intención
# =====================================================================
_PALABRAS_ES = {
    "que", "es", "de", "la", "el", "los", "las", "un", "una", "unos", "unas",
    "para", "muy", "y", "en", "con", "por", "tu", "tus", "lo", "del", "al",
    "se", "su", "sus", "mi", "mis", "más", "mas", "pero", "como", "está",
    "esta", "son", "hay", "esto", "eso", "tan", "tiene", "ser", "esos",
    "esa", "ese", "quiero", "dame", "algo", "canción", "cancion", "música",
    "musica", "tema", "ponme", "claro", "perfecto", "entendido", "bueno",
    "quieres", "gustaría", "gustaria", "sería", "seria", "aquí", "ahora",
}


_PALABRAS_EN_META = {
    "mood", "genre", "tempo", "era", "instrumentation", "style", "vibe", "feel",
    "song", "songs", "music", "keywords", "keyword", "english", "description",
    "output", "result", "answer", "response",
}


def validar_keywords_en(texto: str) -> str | None:
    """Acepta solo 2-5 keywords cortas en inglés; si el modelo divagó, None.

    Los modelos pequeños responden cosas como "entendido, que es muy popular y
    tiene un ritmo": eso no son keywords y arruinaría el retrieval, así que se
    rechaza y el agente usa la heurística ES→EN.
    """
    if not texto:
        return None
    limpio = re.sub(r"[^a-zA-Z0-9,\s-]", " ", texto)
    partes: list[str] = []
    for trozo in limpio.split(","):
        palabras = " ".join(trozo.split()).lower().split()
        palabras = [p for p in palabras if p not in _PALABRAS_EN_META]
        if not palabras or len(palabras) > 3:
            continue
        if any(p in _PALABRAS_ES for p in palabras):
            continue
        if any(len(p) < 2 for p in palabras):
            continue
        partes.append(" ".join(palabras))
        if len(partes) == 5:
            break
    if not partes:
        return None
    return ", ".join(dict.fromkeys(partes))[:120]
