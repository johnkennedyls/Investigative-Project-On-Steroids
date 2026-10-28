# scripts/diagnosticar_retrieval.py - Diagnóstico de relevancia del Módulo 2
"""
Responde una batería de pedidos tipo demo (sin LLM, sin red) y mide QUÉ sale
realmente del retrieval. Es la evidencia reproducible de la tesis sobre si el
agente entiende el mood, separada de la telemetría de la API.

    py -3.12 scripts/diagnosticar_retrieval.py            # batería completa
    py -3.12 scripts/diagnosticar_retrieval.py --json r.json

Por cada pedido informa:
  * géneros del top-10 y su distribución (¿"tranquilo" devuelve rock?),
  * cuantiles medios de energía/danza/valor/tristeza del top-10,
  * cobertura del Módulo 3 sobre el pool (por qué no se reordenó),
  * canciones sin título y artistas distintos (diversidad),
  * si el pedido tenía perfil de ánimo aplicado o no,
  * y en la batería continua, si el género pedido sobrevive a los "dame más".

NO calcula Hit Rate / MRR / NDCG: esas métricas necesitan etiquetas de
relevancia que aquí no existen. Lo que este script muestra es un diagnóstico de
coherencia mood→catálogo, con su limitación documentada.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Modo demo determinista: el diagnóstico es del retrieval, no del LLM.
os.environ.setdefault("INTENT_MODE", "heuristica")

import app  # noqa: E402  (carga Módulo 2 y Módulo 3: tarda ~1 min)
import conversacion  # noqa: E402
import perfiles  # noqa: E402

# (mensaje ES, mood esperado). El esperado se comprueba contra los rasgos del
# catálogo: es una hipótesis verificable, no una opinión sobre la lista.
PEDIDOS = [
    ("quiero algo tranquilo para leer", "baja energia y bajo volumen"),
    ("me siento triste y melancólico", "alta tristeza, bajo valor"),
    ("algo para la fiesta con amigos", "alta danza y alta energia"),
    ("música con energía para entrenar", "alta energia y alto volumen"),
    ("pon algo romántico", "alto romantico"),
    ("quiero rock con garra", "genero rock"),
    ("algo de jazz para cenar", "genero jazz"),
    ("musica para concentrarme", "baja energia y baja danza"),
]

# Misma sesión, turnos encadenados: mide si la conversación mantiene el rumbo.
# "dame más" no nombra género, así que sin herencia la tanda viraba a jazz.
CONTINUADAS = [
    ("quiero rock con garra", "genero rock"),
    ("dame más de esa energía", "rock con mas energia"),
    ("algo más tranquilo", "rock mas bajo de energia"),
]


def rasgos_de(id_: str):
    """Cuantiles del catálogo para una canción recomendada (por índice de fila)."""
    indice = app.module2.song_ids.index(id_) if id_ in app.module2.song_ids else None
    if indice is None or app.module2.feat_cuanto is None:
        return {}
    nombres = app.module2.feat_nombre
    fila = app.module2.feat_cuanto[indice]
    return {n: float(fila[i]) for i, n in enumerate(nombres)}


def analizar(mensaje: str, esperado: str, sesion_id: str | None = None) -> dict:
    # Sin sesion explicita cada pedido es un primer turno aislado; la batería
    # continua pasa la misma sesión para medir la coherencia entre turnos.
    sesion_id = sesion_id or f"diag-{abs(hash(mensaje)) % 10**8}"
    resultado = app.procesar_consulta_echopulse(mensaje, sesion_id)
    canciones = resultado["module3_reranked"]

    generos, cuantiles = {}, {}
    sin_titulo = 0
    for c in canciones:
        # Etiqueta canónica (las tres columnas de género del catálogo filtradas),
        # con la pedida primero: `genre_lyr` suelto dice "blues" en canciones que
        # el propio catálogo también marca como rock.
        etiqueta = (c.get("generos") or [c.get("genre") or "sin dato"])[0].strip() or "sin dato"
        generos[etiqueta] = generos.get(etiqueta, 0) + 1
        if c.get("sin_nombre"):
            sin_titulo += 1
        for nombre, valor in rasgos_de(c.get("id", "")).items():
            cuantiles.setdefault(nombre, []).append(valor)

    promedios = {k: round(statistics.mean(v), 3) for k, v in cuantiles.items()}
    keywords = conversacion.detectar_tono(mensaje)[2]
    # El perfil mostrado es el que M2 aplicó de verdad: en un turno de continuación
    # lleva el género heredado, que perfil_consulta del texto actual no vería.
    perfil_aplicado = (
        resultado["evaluacion"].get("perfil")
        or perfiles.describir_perfil(*perfiles.perfil_consulta(resultado["query_en"]))
    )
    cumple = [c.get("cumple_genero") for c in canciones if c.get("cumple_genero") is not None]
    desvios = [c.get("desvio_animo") for c in canciones if c.get("desvio_animo") is not None]
    return {
        "mensaje": mensaje,
        "esperado": esperado,
        "query_en": resultado["query_en"],
        "keywords_heuristica": keywords,
        "perfil_aplicado": perfil_aplicado,
        "tipo_turno": resultado["evaluacion"].get("tipo_turno"),
        "perfil_heredado": resultado["evaluacion"].get("perfil_heredado", False),
        "generos": generos,
        "coherencia_genero": (
            round(sum(1 for x in cumple if x) / len(cumple), 3) if cumple else None
        ),
        "desvio_animo_promedio": round(statistics.mean(desvios), 3) if desvios else None,
        "cuantiles_medios": promedios,
        "sin_titulo": sin_titulo,
        "artistas_distintos": len(
            {c.get("artist_name") for c in canciones if c.get("artist_name")}
        ),
        "emergentes": sum(1 for c in canciones if c.get("emergente")),
        "cobertura_m3": resultado["evaluacion"]["cobertura_m3"],
        "top3": [
            f"«{c.get('track_name') or 'sin título'}» — {c.get('artist_name')} "
            f"[{' · '.join(c.get('generos') or [c.get('genre') or 'sin género'])}]"
            for c in canciones[:3]
        ],
        "respuesta_agente": resultado["response"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", help="ruta donde guardar el reporte JSON")
    args = parser.parse_args()

    def mostrar(r: dict, encabezado: str) -> None:
        print(f"\n{encabezado}  (esperado: {r['esperado']})")
        print(f"    keywords EN : {r['query_en']}")
        print(f"    perfil      : {r['perfil_aplicado']}"
              f"{' · heredado del turno anterior' if r['perfil_heredado'] else ''}")
        print(f"    géneros     : {r['generos']}")
        print(f"    alineación  : género pedido cumplido {r['coherencia_genero']} | "
              f"desvío de ánimo {r['desvio_animo_promedio']} "
              f"(0 = clavado, 1 = opuesto)")
        print(f"    cuantiles   : {r['cuantiles_medios']}")
        print(f"    cobertura M3: {r['cobertura_m3'] * 100:.0f}% | "
              f"artistas {r['artistas_distintos']} | emergentes {r['emergentes']} | "
              f"sin título {r['sin_titulo']}")
        for linea in r["top3"]:
            print(f"      {linea}")

    reportes = []
    for mensaje, esperado in PEDIDOS:
        try:
            r = analizar(mensaje, esperado)
        except Exception as exc:  # un fallo no debe tapar el resto de la batería
            print(f"❌ {mensaje}: {type(exc).__name__}: {exc}")
            continue
        reportes.append(r)
        mostrar(r, f"=== {mensaje}")

    continuada = []
    for i, (mensaje, esperado) in enumerate(CONTINUADAS, start=1):
        try:
            r = analizar(mensaje, esperado, sesion_id="diag-continuada")
        except Exception as exc:
            print(f"❌ [continuación] {mensaje}: {type(exc).__name__}: {exc}")
            break
        continuada.append(r)
        mostrar(r, f">>> turno {i} · {mensaje} · tipo {r['tipo_turno']}")

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {
                    "generado": datetime.now().isoformat(),
                    "filas_catalogo": int(len(app.module2.df_ref))
                    if app.module2.df_ref is not None
                    else 0,
                    "clases_modulo3": int(len(app.module3.song2idx)),
                    "limitacion": (
                        "Diagnóstico de coherencia mood→catálogo. No es accuracy: "
                        "las métricas de ranking (HR/Recall/Precision/MRR/NDCG) "
                        "requieren etiquetas de relevancia."
                    ),
                    "pedidos": reportes,
                    "continuada": continuada,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\n📄 Reporte guardado en {args.json}")
    print(f"\n✅ {len(reportes)}/{len(PEDIDOS)} pedidos diagnosticados "
          f"+ {len(continuada)}/{len(CONTINUADAS)} turnos de conversación continua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
