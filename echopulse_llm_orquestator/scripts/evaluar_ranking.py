# evaluar_ranking.py - HR@1, Recall@10, MRR y NDCG@10 sobre los turnos registrados
"""
Evaluación offline del ranking que produjo la demo desplegada.

No inventa etiquetas de preferencia: la relevancia se operacionaliza como
**afinidad de contenido verificable**, es decir, si las pistas devueltas cumplen
de verdad la restricción de género y de ánimo que el propio turno prometió
(`calidad.perfil`, la misma que el agente anunció en voz alta). Las etiquetas
vienen del catálogo (Tabla Maestra: genre_lyr/genre_was/album_genre y los
rasgos numéricos convertidos a cuantiles), no del ranking del sistema, así que
la métrica puede fallarle.

Conjunto relevante R(q): las <=10 pistas del catálogo que mejor satisfacen la
promesa (desvío de ánimo creciente, desempate por msd_id para que el corte no
use información léxica ni neuronal de ningún candidato). Sobre R(q) se calculan
las cuatro métricas para el ranking registrado del sistema y para tres líneas
base que también compiten por las mismas 10 posiciones.

Uso (dentro del contenedor de la VM, donde viven /app/logs y el parquet):
    python evaluar_ranking.py --salida /tmp/ranking.json
Local (repo clonado, logs descargados en una carpeta):
    python scripts/evaluar_ranking.py --logs C:/ruta/logs/events_*.jsonl
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
for candidato in (RAIZ, Path("/app")):
    if (candidato / "perfiles.py").exists():
        sys.path.insert(0, str(candidato))
        break
import perfiles  # noqa: E402

# Banda de ánimo: un desvío de 0,25 en cuantiles significa que la pista está a
# un cuarto del catálogo del objetivo pedido. Es el umbral con el que se juzga;
# se reportan también 0,15 y 0,35 para que se vea que la comparación no cambia
# de orden si la banda se aprieta o se afloja.
UMBRAL_ANIMO = 0.25
UMBRALES_SENSIBILIDAD = (0.15, 0.35)
TOP_K = 10


def norm(texto) -> str:
    """Clave de join: minúsculas, sin acentos, sin signos, espacios colapsados."""
    s = unicodedata.normalize("NFKD", str(texto or "").lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


# ---------------------------------------------------------------------------
# Insumos
# ---------------------------------------------------------------------------
def cargar_catalogo(ruta_parquet: str) -> dict:
    df = pd.read_parquet(ruta_parquet)
    col_track = next(c for c in df.columns if c.lower() in ("track_title", "track_name"))
    col_artist = next(c for c in df.columns if c.lower() in ("artist_name", "artist"))
    col_id = "msd_id" if "msd_id" in df.columns else df.columns[0]

    def _texto(nombre):
        serie = df.get(nombre)
        return serie.fillna("").astype(str) if serie is not None else ""

    mezcla = _texto("genre_lyr") + " | " + _texto("genre_was") + " | " + _texto("album_genre")
    generos = [perfiles.canonicos(g) for g in mezcla]

    nombres, bloques = [], []
    for rasgo in perfiles.FEATURES:
        serie = df.get(rasgo)
        if serie is None:
            continue
        valores = pd.to_numeric(serie, errors="coerce")
        if valores.notna().sum() < 2:
            continue
        nombres.append(rasgo)
        bloques.append(valores.fillna(valores.median()).to_numpy(dtype="float64"))
    cuantiles = perfiles.cuantiles(np.column_stack(bloques)) if bloques else None

    ids = [str(v) for v in df[col_id]]
    pares = {(norm(a), norm(t)): i for i, (a, t) in enumerate(zip(df[col_artist], df[col_track]))
             if norm(t)}
    return {
        "n": len(df),
        "ids": ids,
        "artistas": [str(v) for v in df[col_artist]],
        "títulos": [str(v) for v in df[col_track]],
        "generos": generos,
        "feat_nombre": nombres,
        "cuantiles": cuantiles,
        "por_id": {i: k for k, i in enumerate(ids)},
        "por_par": pares,
        "popularity": np.zeros(len(df), dtype=np.float64),
    }


def cargar_popularidad(cat: dict, rutas: list[str]) -> dict:
    """Popularidad Spotify por fila, con la misma doble señal que usa la app:
    (artista, título) y, como respaldo, la máxima fama del artista."""
    por_artista, por_par = {}, {}
    for ruta in rutas:
        if not Path(ruta).exists():
            continue
        try:
            f = pd.read_parquet(ruta)
        except Exception:
            continue
        for tipo, a, t, p in zip(f["tipo"], f["artista_n"], f["titulo_n"], f["pop"]):
            p = int(p)
            if tipo == "artista":
                por_artista[a] = max(por_artista.get(a, 0), p)
            else:
                por_par.setdefault((a, t), p)

    def fila(i):
        a, t = norm(cat["artistas"][i]), norm(cat["títulos"][i])
        return por_par.get((a, t)) or por_artista.get(a)

    valores = [fila(i) for i in range(cat["n"])]
    cat["popularity"] = np.array([v if v is not None else 0 for v in valores], dtype=np.float64)
    return {
        "fuentes": [str(Path(r)) for r in rutas if Path(r).exists()],
        "con_popularidad": int(sum(1 for v in valores if v is not None)),
        "total": cat["n"],
    }


def leer_eventos(pattern: str) -> list[dict]:
    eventos = []
    for ruta in sorted(glob.glob(pattern)):
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    e = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                if e.get("ranking"):
                    eventos.append(e)
    eventos.sort(key=lambda e: (e.get("timestamp") or ""))
    return eventos


# ---------------------------------------------------------------------------
# Ground truth derivada del catálogo
# ---------------------------------------------------------------------------
def parsear_perfil(texto: str) -> tuple[set[str], dict[str, float]]:
    """'genre=rock mood=energy_lyr:0.85,val_lyr:0.70' -> ({'rock'}, {...})."""
    generos: set[str] = set()
    animo: dict[str, float] = {}
    for token in str(texto or "").split():
        if token.startswith("genre="):
            generos |= {g for g in token[6:].split("/") if g}
        elif token.startswith("mood="):
            for par in token[5:].split(","):
                if ":" in par:
                    k, v = par.split(":", 1)
                    try:
                        animo[k] = float(v)
                    except ValueError:
                        pass
    return generos, animo


def desvio_matrix(cat: dict, animo: dict[str, float]) -> np.ndarray | None:
    return perfiles.distancia_animo(animo, cat["feat_nombre"], cat["cuantiles"])


def mask_genero(cat: dict, generos: set[str]) -> np.ndarray | None:
    return perfiles.desvio_genero(generos, cat["generos"])


def cumplimiento(cat: dict, generos: set[str], animo: dict[str, float], umbral: float):
    """(máscara, desvío) de las pistas que cumplen la promesa, o None si no hay promesa."""
    if not generos and not animo:
        return None
    cumple = np.ones(cat["n"], dtype=bool)
    desvio = np.zeros(cat["n"], dtype=np.float64)
    if generos:
        m = mask_genero(cat, generos)
        if m is None:
            return None
        cumple &= m == 0.0
    if animo:
        d = desvio_matrix(cat, animo)
        if d is None:
            return None
        desvio = d.astype(np.float64)
        cumple &= desvio <= umbral
    return cumple, desvio


def relevantes_de(cat: dict, ids_arr: np.ndarray, cumple: np.ndarray, desvio: np.ndarray):
    """R(q): las <=10 pistas que mejor cumplen, orden por desvío y msd_id."""
    idx = np.flatnonzero(cumple)
    if idx.size == 0:
        return [], idx, None
    orden = idx[np.lexsort((ids_arr[idx], desvio[idx]))]
    return [cat["ids"][i] for i in orden[:TOP_K]], idx, float(desvio[idx].mean())


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------
def dcg(ganos: list[int]) -> float:
    return sum(g / np.log2(i + 2) for i, g in enumerate(ganos))


def metricas_uma(ranking: list[str], relevante: set[str], corte: int = TOP_K) -> dict:
    """Métricas de un método sobre el mismo corte de 10 posiciones.

    Un método que entrega menos de 10 (las 3 tarjetas visibles) se rellena con
    vacíos: sigue compitiendo en las 10 plazas, así que Recall@10 y NDCG@10 son
    comparables con los de un sistema que sí llena la pantalla.
    """
    top = (list(ranking[:corte]) + [None] * corte)[:corte]
    aciertos = [1 if i is not None and i in relevante else 0 for i in top]
    pos = next((k + 1 for k, i in enumerate(top) if i is not None and i in relevante), 0)
    idcg = dcg([1] * min(len(relevante), corte))
    return {
        "hr1": aciertos[0],
        "hr3": 1 if any(aciertos[:3]) else 0,
        "prec10": float(np.mean(aciertos)),
        "recall10": (sum(aciertos) / len(relevante)) if relevante else 0.0,
        "rr": (1.0 / pos) if pos else 0.0,
        "ndcg10": (dcg(aciertos) / idcg) if idcg else 0.0,
    }


def metricas_gradadas(
    ranking: list[str],
    cat: dict,
    cumple: np.ndarray,
    desvio: np.ndarray,
    ideal_ids: list[str],
    corte: int = TOP_K,
) -> dict:
    """Protocolo principal: relevancia gradada sobre TODAS las pistas que cumplen.

    Una pista es relevante si pertenece al género pedido y su desvío de ánimo no
    pasa el umbral; la ganancia no es binaria sino `1 - desvío`, de modo que una
    canción que cumple de sobra vale más que una que cumple por los pelos. El
    IDCG sale de las diez que mejor cumplen en el catálogo entero (el mismo
    oracle que usa `relevantes_de`), así que NDCG@10 sigue acotado en [0,1].

    Recall@10 divide entre min(|R|, 10): cuando el catálogo tiene 800 pistas que
    cumplen, exigir las 800 en diez plazas no mide el sistema sino el tamaño del
    catálogo. Es la convención habitual cuando |R| >> k y se declara explícita.
    """
    top = (list(ranking[:corte]) + [None] * corte)[:corte]
    ganancias, aciertos = [], []
    for ident in top:
        i = cat["por_id"].get(ident) if ident is not None else None
        if i is not None and bool(cumple[i]):
            ganancias.append(float(1.0 - desvio[i]))
            aciertos.append(1)
        else:
            ganancias.append(0.0)
            aciertos.append(0)
    pos = next((k + 1 for k, a in enumerate(aciertos) if a), 0)
    n_rel = int(cumple.sum())
    idcg = dcg([float(1.0 - desvio[cat["por_id"][x]]) for x in ideal_ids])
    return {
        "hr1": aciertos[0],
        "hr3": 1 if any(aciertos[:3]) else 0,
        "prec10": float(np.mean(aciertos)),
        "recall10": (sum(aciertos) / min(n_rel, corte)) if n_rel else 0.0,
        "rr": (1.0 / pos) if pos else 0.0,
        "ndcg10": (dcg(ganancias) / idcg) if idcg else 0.0,
    }


def agregar(filas: list[dict]) -> dict:
    if not filas:
        return {}
    salida = {}
    for clave in ("hr1", "hr3", "prec10", "recall10", "rr", "ndcg10"):
        valores = [f[clave] for f in filas]
        salida[clave] = float(np.mean(valores))
        salida[clave + "_se"] = float(np.std(valores, ddof=1) / np.sqrt(len(valores))) if len(valores) > 1 else 0.0
    return salida


# ---------------------------------------------------------------------------
# Métodos en competencia
# ---------------------------------------------------------------------------
def fila_de(cat: dict, tarjeta: dict) -> int | None:
    i = cat["por_id"].get(str(tarjeta.get("id")))
    if i is not None:
        return i
    return cat["por_par"].get((norm(tarjeta.get("artist_name")), norm(tarjeta.get("track_name"))))


def base_lexica(cat: dict, query_en: str, k: int = TOP_K) -> list[str]:
    """Línea base sin modelo: Jaccard entre las palabras de la consulta y la letra.

    Se apoya en un índice invertido (palabra -> filas) porque recorrer las 5.710
    letras de cada turno no escala en una VM de 2 núcleos.
    """
    terms = perfiles.terms_consulta(query_en)
    if not terms:
        return []
    conteo: dict[int, int] = {}
    for t in terms:
        for i in cat["indice_letras"].get(t, ()):
            conteo[i] = conteo.get(i, 0) + 1
    puntuadas = []
    for i, interseccion in conteo.items():
        j = interseccion / (len(terms) + len(cat["palabras"][i]) - interseccion)
        puntuadas.append((j, i))
    puntuadas.sort(key=lambda t: (-t[0], -cat["popularity"][t[1]], t[1]))
    return [cat["ids"][i] for _, i in puntuadas[:k]]


def indice_de_letras(palabras: list[set[str]]) -> dict[str, tuple[int, ...]]:
    indice: dict[str, set[int]] = {}
    for i, w in enumerate(palabras):
        for palabra in w:
            indice.setdefault(palabra, set()).add(i)
    return {k: tuple(v) for k, v in indice.items()}


# ---------------------------------------------------------------------------
# Evalución
# ---------------------------------------------------------------------------
def evaluar(eventos: list[dict], cat: dict, rng_semilla: int = 20261103) -> dict:
    ids_arr = np.asarray(cat["ids"])
    global_pop = np.argsort(-cat["popularity"], kind="stable")
    base_popularidad = [cat["ids"][i] for i in global_pop[:TOP_K]]
    rng = np.random.default_rng(rng_semilla)

    detalle, omisiones = [], []
    saltos = {"sin_restriccion": 0, "consulta_con_senal_sin_perfil": 0, "catalogo_no_alcanza": 0}
    metodos = ("sistema", "sistema_visible", "aleatorio", "popularidad", "lexica")
    por_metodo = {m: [] for m in metodos}
    por_metodo_amplio = {m: [] for m in metodos}
    por_metodo_gradado = {m: [] for m in metodos}
    por_banda = {u: {m: [] for m in metodos} for u in UMBRALES_SENSIBILIDAD}
    tipos_perfil = {"solo_genero": 0, "solo_animo": 0, "ambos": 0}
    por_tipo = {t: {m: [] for m in metodos} for t in tipos_perfil}
    por_tipo_gradado = {t: {m: [] for m in metodos} for t in tipos_perfil}

    for e in eventos:
        perfil = (e.get("calidad") or {}).get("perfil") or ""
        generos, animo = parsear_perfil(perfil)
        if not generos and not animo:
            g2, a2 = perfiles.perfil_consulta(e.get("query_en") or "")
            if g2 or a2:
                saltos["consulta_con_senal_sin_perfil"] += 1
            else:
                saltos["sin_restriccion"] += 1
            continue

        ids_sistema, faltantes = [], 0
        for tarjeta in e["ranking"]:
            i = fila_de(cat, tarjeta)
            if i is None:
                faltantes += 1
                continue
            ids_sistema.append(cat["ids"][i])
        if faltantes:
            omisiones.append({"id": e.get("id"), "sin_fila": faltantes})

        lista_aleatoria = [cat["ids"][i] for i in rng.choice(cat["n"], size=TOP_K, replace=False)]
        lexica = base_lexica(cat, e.get("query_en") or "")
        tipo = "ambos" if generos and animo else "solo_genero" if generos else "solo_animo"

        for umbral in (UMBRAL_ANIMO,) + UMBRALES_SENSIBILIDAD:
            res = cumplimiento(cat, generos, animo, umbral)
            if res is None:
                break
            cumple, desvio = res
            rel_ids, idx, desvio_medio = relevantes_de(cat, ids_arr, cumple, desvio)
            if not rel_ids:
                if umbral == UMBRAL_ANIMO:
                    saltos["catalogo_no_alcanza"] += 1
                continue
            relevante = set(rel_ids)
            candidato = {
                "sistema": ids_sistema,
                "sistema_visible": ids_sistema[:3],
                "aleatorio": lista_aleatoria,
                "popularidad": base_popularidad,
                "lexica": lexica,
            }
            if umbral in UMBRALES_SENSIBILIDAD:
                # La sensibilidad repite el protocolo principal (gradado) con otra
                # banda de ánimo, para que sus filas sean comparables con la del
                # umbral de referencia y no con la variante binaria.
                for nombre, ranking in candidato.items():
                    por_banda[umbral][nombre].append(
                        metricas_gradadas(ranking, cat, cumple, desvio, rel_ids))
            else:
                for nombre, ranking in candidato.items():
                    por_metodo[nombre].append(metricas_uma(ranking, relevante))
            if umbral != UMBRAL_ANIMO:
                continue
            amplios = {cat["ids"][i] for i in idx}
            for nombre, ranking in candidato.items():
                por_metodo_amplio[nombre].append(metricas_uma(ranking, amplios))
                grad = metricas_gradadas(ranking, cat, cumple, desvio, rel_ids)
                por_metodo_gradado[nombre].append(grad)
                por_tipo[tipo][nombre].append(metricas_uma(ranking, relevante))
                por_tipo_gradado[tipo][nombre].append(grad)
            tipos_perfil[tipo] += 1
            detalle.append({
                "id": e.get("id"),
                "turno": e.get("turno"),
                "sesion": (e.get("session_id") or "")[:8],
                "query": (e.get("query_en") or "")[:60],
                "perfil": perfil,
                "tipo": tipo,
                "n_cumplen": int(idx.size),
                "relevante": len(relevante),
                "desvio_medio": desvio_medio,
                "cobertura_ranking": len(ids_sistema) / max(1, len(e["ranking"])),
                "aciertos_top10": sum(1 for i in ids_sistema[:TOP_K] if i in relevante),
                "aciertos_visibles": sum(1 for i in ids_sistema[:3] if i in relevante),
                "rank_primero": next((k + 1 for k, i in enumerate(ids_sistema) if i in relevante), 0),
                **por_metodo["sistema"][-1],
                **{f"g_{k}": v for k, v in por_metodo_gradado["sistema"][-1].items()},
                "emergentes_visibles": sum(1 for t in e["ranking"][:3] if t.get("emergente")),
                "emergentes_internos": sum(1 for t in e["ranking"] if t.get("emergente")),
                "proveedor": (e.get("calidad") or {}).get("llm_proveedor"),
                "latencia_ms": (e.get("latencies_ms") or {}).get("total"),
            })

    juzgados = len(detalle)
    return {
        "turnos_procesados": len(eventos),
        "turnos_juzgados": juzgados,
        "saltos": saltos,
        "tipos_perfil": tipos_perfil,
        "turnos_sin_fila_en_catalogo": len(omisiones),
        "agregado": {m: agregar(v) for m, v in por_metodo.items()},
        "agregado_gradado": {m: agregar(v) for m, v in por_metodo_gradado.items()},
        "agregado_amplio": {m: agregar(v) for m, v in por_metodo_amplio.items()},
        "por_tipo_perfil": {t: {m: agregar(v) for m, v in d.items()} for t, d in por_tipo.items()},
        "por_tipo_gradado": {t: {m: agregar(v) for m, v in d.items()}
                             for t, d in por_tipo_gradado.items()},
        "sensibilidad": {
            str(u): {m: agregar(v) for m, v in por_banda[u].items()} for u in UMBRALES_SENSIBILIDAD
        },
        "tamano_relevante_media": float(np.mean([d["relevante"] for d in detalle])) if detalle else 0,
        "promesas_satisfacibles": (juzgados / (juzgados + saltos["catalogo_no_alcanza"]))
        if (juzgados + saltos["catalogo_no_alcanza"]) else 0,
        "detalle": detalle,
        "omisiones": omisiones[:20],
    }


def main():
    parser = argparse.ArgumentParser()
    temp = os.environ.get("TEMP", "/tmp")
    parser.add_argument("--logs", default="/app/logs/events_*.jsonl" if Path("/app/logs").exists()
                        else os.path.join(temp, "eva", "events_*.jsonl"))
    parser.add_argument("--catalogo", default=None)
    parser.add_argument("--fama", default=None,
                        help="fame_index.parquet (lista separada por comas o ;)")
    parser.add_argument("--salida", default=os.path.join(temp, "eva", "ranking.json"))
    args = parser.parse_args()

    ruta_parquet = args.catalogo
    if ruta_parquet and any(c in ruta_parquet for c in "*?["):
        coincidencias = sorted(glob.glob(ruta_parquet))
        if not coincidencias:
            raise SystemExit(f"--catalogo no encontró archivos: {ruta_parquet}")
        ruta_parquet = coincidencias[0]
    if not ruta_parquet:
        candidatos = sorted(glob.glob("/app/tabla_maestra/**/*.parquet", recursive=True)) or \
                   sorted(glob.glob(str(RAIZ.parent / "tabla_maestra" / "**" / "*.parquet"),
                                    recursive=True))
        if not candidatos:
            raise SystemExit("No se encontró el parquet de la Tabla Maestra (usa --catalogo).")
        ruta_parquet = candidatos[0]

    cat = cargar_catalogo(ruta_parquet)
    rutas_fama = [p.strip() for p in re.split(r"[;,]", args.fama) if p.strip()] if args.fama else [
        "/app/models/fame_index.parquet",
        str(RAIZ / "models" / "fame_index.parquet"),
    ]
    pop_info = cargar_popularidad(cat, rutas_fama)
    # palabras de la letra: se construyen una vez y solo si hace falta la línea léxica
    df = pd.read_parquet(ruta_parquet)
    col_letra = "lyrics_cleaned" if "lyrics_cleaned" in df.columns else "lyrics"
    cat["palabras"] = [set(str(v).split()) for v in df[col_letra].fillna("")]
    cat["indice_letras"] = indice_de_letras(cat["palabras"])

    eventos = leer_eventos(args.logs)
    resultado = evaluar(eventos, cat)
    resultado["insumos"] = {
        "parquet": str(ruta_parquet),
        "pistas": cat["n"],
        "rasgos": cat["feat_nombre"],
        "popularidad": pop_info,
        "logs": args.logs,
        "umbral_animo": UMBRAL_ANIMO,
        "semilla": 20261103,
        "protocolo": {
            "gradado": "R = toda pista del género pedido con desvío de ánimo <= umbral; "
                       "ganancia = 1 - desvío; Recall@10 sobre min(|R|,10); "
                       "IDCG con las 10 mejores del catálogo",
            "oracle10": "R = las 10 pistas de menor desvío dentro del género pedido; "
                        "ganancia binaria; Recall@10 sobre |R|",
            "amplio": "R = toda pista que cumple; ganancia binaria; Recall@10 sobre |R|",
        },
    }

    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    with open(args.salida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False)

    lineas = [f"turnos juzgados: {resultado['turnos_juzgados']} / {len(eventos)}"]
    for etiqueta, clave in (("gradado", "agregado_gradado"), ("oracle10", "agregado"),
                            ("amplio", "agregado_amplio")):
        lineas.append(f"-- relevancia {etiqueta} --")
        for nombre, m in resultado[clave].items():
            if m:
                lineas.append(
                    f"{nombre:18s} HR@1={m['hr1']:.3f} Recall@10={m['recall10']:.3f} "
                    f"MRR={m['rr']:.3f} NDCG@10={m['ndcg10']:.3f}"
                )
    print("\n".join(lineas))
    print(f"salida: {args.salida}")


if __name__ == "__main__":
    main()
