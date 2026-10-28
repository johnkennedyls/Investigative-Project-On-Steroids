# perfiles.py - Señal de género y ánimo para el retrieval (Módulo 2)
"""
La tabla maestra trae el género predicho (`genre_lyr`, `genre_was`,
`album_genre`) y rasgos de ánimo numéricos (`energy_lyr`, `dance_lyr`,
`val_lyr`, `sadness`, `romantic`, `loud_lyr`). El retrieval solo usaba
similitud neuronal + Jaccard lírico: ninguna de las dos compara el mood
pedido con el mood de la canción, así que "algo tranquilo" podía devolver
hard rock.

Este módulo convierte las keywords de la consulta (EN) en un objetivo de
género + cuantiles de ánimo y lo compara contra el catálogo. Puro numpy /
sin torch para poder probarlo sin cargar los modelos.
"""

from __future__ import annotations

import re

import numpy as np

# Rasgos numéricos que existen en TODAS las filas de la tabla maestra.
FEATURES: tuple[str, ...] = (
    "energy_lyr", "dance_lyr", "val_lyr", "sadness", "romantic", "loud_lyr",
)

# Géneros realmente presentes en el catálogo (value_counts de genre_lyr):
# pop, rock, country, blues, jazz, reggae, hip hop. Un alias que no exista
# aquí no aporta señal y se ignora.
GENERO_CANONICO: dict[str, str] = {
    "rock": "rock", "metal": "rock", "heavy": "rock", "punk": "rock",
    "grunge": "rock", "guitar": "rock", "garage": "rock",
    "pop": "pop", "comercial": "pop", "radio": "pop",
    "country": "country", "folk": "country", "acoustic": "country",
    "jazz": "jazz", "swing": "jazz", "blues": "blues", "soul": "blues",
    "reggae": "reggae", "ska": "reggae", "dub": "reggae",
    "rap": "hip hop", "hip": "hip hop", "hop": "hip hop", "trap": "hip hop",
    "urban": "hip hop",
}

# Targets de ánimo como cuantiles [0,1]: 0.2 = bajo, 0.5 = medio, 0.85 = alto.
# Se expresan como cuantiles (no valores crudos) porque rasgos como `sadness`
# están muy sesgados (mediana 0.03, p75 0.28).
PERFIL_ANIMO: dict[str, dict[str, float]] = {
    "sad": {"sadness": 0.80, "val_lyr": 0.20, "energy_lyr": 0.30, "loud_lyr": 0.25},
    "melancholic": {"sadness": 0.80, "val_lyr": 0.25, "energy_lyr": 0.30},
    "heartbreak": {"sadness": 0.85, "val_lyr": 0.20, "romantic": 0.60},
    "depress": {"sadness": 0.85, "val_lyr": 0.15, "energy_lyr": 0.25},
    "lonely": {"sadness": 0.75, "val_lyr": 0.25, "energy_lyr": 0.30},
    "happy": {"val_lyr": 0.80, "energy_lyr": 0.65, "sadness": 0.15},
    "upbeat": {"val_lyr": 0.80, "energy_lyr": 0.75, "sadness": 0.15},
    "feel": {"val_lyr": 0.75, "dance_lyr": 0.65},
    "good": {"val_lyr": 0.70, "energy_lyr": 0.60},
    "glorious": {"val_lyr": 0.80, "energy_lyr": 0.80},
    "party": {"dance_lyr": 0.80, "energy_lyr": 0.80, "val_lyr": 0.70},
    "dance": {"dance_lyr": 0.85, "energy_lyr": 0.75},
    "danceable": {"dance_lyr": 0.85, "energy_lyr": 0.75},
    "disco": {"dance_lyr": 0.85, "val_lyr": 0.70},
    "calm": {"energy_lyr": 0.20, "loud_lyr": 0.20, "dance_lyr": 0.25},
    "relax": {"energy_lyr": 0.20, "loud_lyr": 0.20, "val_lyr": 0.55},
    "relaxing": {"energy_lyr": 0.20, "loud_lyr": 0.20, "val_lyr": 0.55},
    "chill": {"energy_lyr": 0.25, "loud_lyr": 0.25, "dance_lyr": 0.30},
    "soft": {"energy_lyr": 0.20, "loud_lyr": 0.15},
    "gentle": {"energy_lyr": 0.20, "loud_lyr": 0.15, "val_lyr": 0.50},
    "slow": {"energy_lyr": 0.25, "dance_lyr": 0.20},
    "quiet": {"energy_lyr": 0.15, "loud_lyr": 0.15},
    "peaceful": {"energy_lyr": 0.20, "loud_lyr": 0.20, "val_lyr": 0.55},
    "acoustic": {"energy_lyr": 0.35, "loud_lyr": 0.25},
    "energetic": {"energy_lyr": 0.85, "loud_lyr": 0.80, "dance_lyr": 0.60},
    "motivational": {"energy_lyr": 0.80, "val_lyr": 0.70},
    "powerful": {"energy_lyr": 0.85, "loud_lyr": 0.85},
    "gym": {"energy_lyr": 0.85, "dance_lyr": 0.70},
    "angry": {"energy_lyr": 0.90, "loud_lyr": 0.90, "val_lyr": 0.30},
    "aggressive": {"energy_lyr": 0.90, "loud_lyr": 0.90, "val_lyr": 0.25},
    "romantic": {"romantic": 0.80, "val_lyr": 0.60, "energy_lyr": 0.40},
    "love": {"romantic": 0.75, "val_lyr": 0.65},
    "instrumental": {"energy_lyr": 0.35, "loud_lyr": 0.30},
    "piano": {"energy_lyr": 0.30, "loud_lyr": 0.25},
    "classical": {"energy_lyr": 0.30, "loud_lyr": 0.25, "val_lyr": 0.45},
    "orchestral": {"energy_lyr": 0.45, "loud_lyr": 0.40},
    "focus": {"energy_lyr": 0.30, "dance_lyr": 0.25, "loud_lyr": 0.25},
    "summer": {"val_lyr": 0.75, "dance_lyr": 0.65, "energy_lyr": 0.65},
    "beach": {"val_lyr": 0.75, "dance_lyr": 0.70},
    "night": {"val_lyr": 0.35, "energy_lyr": 0.50},
    "rainy": {"val_lyr": 0.30, "energy_lyr": 0.35, "sadness": 0.50},
    "winter": {"val_lyr": 0.30, "energy_lyr": 0.35},
    "retro": {"energy_lyr": 0.55, "val_lyr": 0.60},
    "vintage": {"energy_lyr": 0.50, "val_lyr": 0.55},
}

_PALABRAS_META = {
    "mood", "genre", "tempo", "era", "style", "vibe", "song", "songs",
    "music", "keywords", "like", "sounds", "sound", "track", "very", "more",
    "some", "with", "that", "this", "from", "about",
}


def terms_consulta(query_en: str) -> set[str]:
    """Palabras normalizadas de la consulta, sin meta-palabras ni ruido."""
    crudo = re.sub(r"[^a-z0-9\s]", " ", str(query_en or "").lower()).split()
    salida: set[str] = set()
    for t in crudo:
        if t in _PALABRAS_META or len(t) < 3:
            continue
        salida.add(t)
    # "hip hop" llega como dos términos: ambos apuntan al mismo género.
    return salida


def perfil_consulta(query_en: str) -> tuple[set[str], dict[str, float]]:
    """(géneros canónicos pedidos, targets de ánimo) para una consulta EN.

    Vacío si la consulta no menciona ni género ni ánimo: el llamador debe
    descartar el componente en ese caso (no hay señal que ponderar).
    """
    terms = terms_consulta(query_en)
    generos: set[str] = set()
    animo: dict[str, float] = {}

    for t in terms:
        if t in GENERO_CANONICO:
            generos.add(GENERO_CANONICO[t])
        # "hip hop" sin separador y prefijos/raíces ("danceable" ~ "dance")
        for clave, gen in GENERO_CANONICO.items():
            if " " not in clave and (t.startswith(clave) or clave.startswith(t)) and len(clave) >= 4:
                generos.add(gen)
        for clave, objetivos in PERFIL_ANIMO.items():
            if t == clave:
                for f, v in objetivos.items():
                    # Si dos palabras piden valores opuestos, se promedian.
                    animo[f] = round((animo.get(f, v) + v) / 2, 3) if f in animo else v
            elif len(clave) >= 5 and (t.startswith(clave) or clave.startswith(t)):
                for f, v in objetivos.items():
                    animo[f] = round((animo.get(f, v) + v) / 2, 3) if f in animo else v

    return generos, animo


def heredar_perfil(
    generos: set[str],
    animo: dict[str, float],
    herencia: tuple[list[str], dict[str, float]] | None,
) -> tuple[set[str], dict[str, float], bool]:
    """(géneros, ánimo, ¿hubo herencia?) mezclando el turno actual con el previo.

    "dame más de esa energía" solo cambia el ánimo: si el género no se menciona,
    se arrastra el del turno anterior. Se hereda todo-o-nada por componente —
    mezclar target por target dejaría "tranquilo" heredado discutiendo con la
    "energía" que el usuario acaba de pedir.
    """
    if not herencia:
        return generos, animo, False
    prev_gen, prev_animo = herencia
    heredado = False
    if not generos and prev_gen:
        generos, heredado = set(prev_gen), True
    if not animo and prev_animo:
        animo = dict(prev_animo)
        heredado = True
    return generos, animo, heredado


def canonicos(texto: str) -> set[str]:
    """Etiquetas de género legibles de una fila, sin tokens sueltos de las frases.

    El catálogo trae `genre_lyr`, `genre_was` y `album_genre` como texto libre
    ("rock and roll", "rhythm and blues"). Tokenizar en crudo dejaba etiquetas
    absurdas ('and', 'music', 'roll') y "hip hop" nunca coincidía porque se partía
    en dos tokens. Aquí solo quedan nombres canónicos, que son además los que se
    muestran en la ficha de la canción.
    """
    tokens = re.sub(r"[^a-z0-9 ]", " ", str(texto or "").lower()).split()
    return {GENERO_CANONICO[t] for t in tokens if t in GENERO_CANONICO}


def cuantiles(matriz: np.ndarray) -> np.ndarray:
    """Convierte una matriz (filas x rasgos) en cuantiles por columna [0,1]."""
    matriz = np.asarray(matriz, dtype=np.float64)
    n = matriz.shape[0]
    if n < 2:
        return np.zeros_like(matriz)
    out = np.empty_like(matriz)
    for c in range(matriz.shape[1]):
        orden = np.argsort(np.argsort(matriz[:, c]))
        out[:, c] = orden / (n - 1)
    return out.astype(np.float32)


def perfil_vector(
    generos_pedido: set[str],
    animo_pedido: dict[str, float],
    generos_fila: list[set[str]],
    feat_nombre: list[str],
    cuantil_fila: np.ndarray | None,
) -> np.ndarray | None:
    """Score de perfil [0,1] para todo el catálogo, o None si no hay señal.

    - género: 1.0 si la fila tiene un género pedido, 0.0 si no
    - ánimo: 1 - |cuantil de la fila - cuantil pedido|, promediado
    Si la consulta pide ambos, se combinan 50/50; si pide uno solo, ese manda.
    `feat_nombre` dice qué columna de `cuantil_fila` es cada rasgo (el catálogo
    puede no traer alguno; entonces ese objetivo se ignora, no se fuerza a 0).
    """
    if not generos_pedido and not animo_pedido:
        return None

    partes: list[np.ndarray] = []

    if generos_pedido:
        partes.append(
            np.fromiter(
                (1.0 if (gs & generos_pedido) else 0.0 for gs in generos_fila),
                dtype=np.float32,
                count=len(generos_fila),
            )
        )

    if animo_pedido and cuantil_fila is not None and len(feat_nombre):
        cols, objetivos = [], []
        for f, v in animo_pedido.items():
            if f in feat_nombre:
                cols.append(feat_nombre.index(f))
                objetivos.append(v)
        if cols:
            desvio = np.abs(cuantil_fila[:, cols] - np.asarray(objetivos, dtype=np.float32))
            partes.append((1.0 - desvio.mean(axis=1)).astype(np.float32))

    if not partes:
        return None
    puntaje = np.mean(np.vstack(partes), axis=0)
    return puntaje


def distancia_animo(
    animo_pedido: dict[str, float],
    feat_nombre: list[str],
    cuantil_fila: np.ndarray | None,
) -> np.ndarray | None:
    """Desvío medio [0,1] de cada fila frente al ánimo pedido (0 = clavado).

    `perfil_vector` ya premia la cercanía, pero como una señal más del blend:
    con peso 0.35 una canción de energía opuesta aún puede colar por similitud
    neural. Este desvio se usa como castigo multiplicativo aparte, así que el
    filtro de ánimo no depende de cuánta señal aporte el resto de señales.
    """
    if not animo_pedido or cuantil_fila is None or not len(feat_nombre):
        return None
    cols, objetivos = [], []
    for f, v in animo_pedido.items():
        if f in feat_nombre:
            cols.append(feat_nombre.index(f))
            objetivos.append(v)
    if not cols:
        return None
    desvio = np.abs(cuantil_fila[:, cols] - np.asarray(objetivos, dtype=np.float32))
    return desvio.mean(axis=1).astype(np.float32)


def desvio_genero(generos_pedido: set[str], generos_fila: list[set[str]]) -> np.ndarray | None:
    """1.0 para filas fuera del género pedido, 0.0 para las que están dentro.

    Igual que el ánimo: dentro del blend el género solo vota (peso 0.35 sobre
    un pool ya parecido). "rock con garra" devolvía blues porque la letra y la
    similitud neural pesan más que la etiqueta. Este desvío permite castigar.
    """
    if not generos_pedido:
        return None
    return np.fromiter(
        (0.0 if (gs & generos_pedido) else 1.0 for gs in generos_fila),
        dtype=np.float32,
        count=len(generos_fila),
    )


def describir_perfil(generos: set[str], animo: dict[str, float]) -> str:
    """Etiqueta legible del perfil aplicado (para logs y métricas)."""
    if not generos and not animo:
        return "sin perfil"
    partes = []
    if generos:
        partes.append("genre=" + "/".join(sorted(generos)))
    if animo:
        partes.append("mood=" + ",".join(f"{k}:{v:.2f}" for k, v in sorted(animo.items())))
    return " ".join(partes)
