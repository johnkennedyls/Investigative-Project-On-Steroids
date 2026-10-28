# rerank.py - Fusión Módulo 2 / Módulo 3 con cobertura medida
"""
El re-ranker (Módulo 3) clasifica entre ~38 mil canciones, pero el pool de
retrieval (Módulo 2) sale de una tabla maestra de 5,710 filas: no todas las
candidatas están entre las clases del Modelo 3. Antes, una candidata ausente
recibía `intent_score = 0.0`, lo que la hundía frente a las conocidas y hacía
invisible la causa (una tanda entera podía salir con intención 0 sin que
nadie lo supiera).

Aquí se separa la aritmética del modelo (torch) de la fusión de scores para
poder probarla sin cargar checkpoints:
  * las candidatas que el Módulo 3 conoce se normalizan por su máximo,
  * las desconocidas reciben la mediana de las conocidas (neutro: ni premio
    ni castigo) y se marcan,
  * se devuelve la cobertura del Módulo 3 sobre el pool, que es la métrica
    que falta en la tesis para explicar por qué una tanda no se reordenó.
"""

from __future__ import annotations

from statistics import median

PESO_SIMILITUD = 0.70
PESO_INTENCION = 0.30


def fusionar(
    candidatos: list[dict],
    probabilidades: dict[str, float],
    peso_similitud: float = PESO_SIMILITUD,
    peso_intencion: float = PESO_INTENCION,
) -> tuple[list[dict], dict]:
    """Devuelve (candidatas re-ordenadas, diagnóstico de cobertura).

    `probabilidades` mapea id -> probabilidad del Módulo 3, solo para las
    candidatas que existen como clase en el modelo.
    """
    conocidas = [
        (c, probabilidades[c["id"]])
        for c in candidatos
        if c.get("id") in probabilidades
    ]
    max_p = max((p for _, p in conocidas), default=0.0)
    normales = [p / max_p for _, p in conocidas] if max_p > 0 else []
    neutro = round(median(normales), 4) if normales else 0.0

    cobertura = len(conocidas) / len(candidatos) if candidatos else 0.0
    n_ajustadas = sum(1 for c in candidatos if c.get("id") not in probabilidades)

    scored: list[dict] = []
    for c in candidatos:
        sim = float(c.get("similarity", 0.0) or 0.0)
        if c.get("id") in probabilidades and max_p > 0:
            intent = (probabilidades[c["id"]] / max_p)
            conocida = True
        elif conocidas and neutro > 0:
            intent = neutro
            conocida = False
        else:
            intent = 0.0
            conocida = False
        item = dict(c)
        item["intent_score"] = round(intent, 4)
        item["intent_conocida"] = conocida
        item["final_score"] = round(
            peso_similitud * sim + peso_intencion * intent, 4
        )
        scored.append(item)

    scored.sort(key=lambda x: x["final_score"], reverse=True)
    for i, item in enumerate(scored):
        item["rank"] = i + 1

    diagnostico = {
        "cobertura_m3": round(cobertura, 4),
        "intent_neutra": neutro,
        "candidatas_sin_clase_m3": n_ajustadas,
        "m3_aporto_orden": bool(conocidas and max_p > 0),
    }
    return scored, diagnostico
