# scripts/evaluar_metricas.py
# Métricas de ranking para la tesis, calculadas OFFLINE con lo que guarda el agente.
#
#   logs/events_*.jsonl    → un registro por turno: consulta, respuesta y ranking
#                            completo con rank, similarity e intent_score.
#   logs/feedback_*.jsonl  → la etiqueta del usuario sobre ese turno (gust/no_gust)
#                            más la canción que destacó.
#
# Sin feedback no hay ground truth: las métricas de ranking NO se pueden derivar de
# los contadores de operación (latencia, cobertura M3…). Eso es telemetría.
#
# Uso (dentro del contenedor desplegado):
#   python scripts/evaluar_metricas.py
#   python scripts/evaluar_metricas.py --logs /app/logs --salve informe_evaluacion.md
#   python scripts/evaluar_metricas.py --json informe_evaluacion.json
import argparse
import glob
import json
import math
import os
import re
import unicodedata
from collections import Counter

Ks = (1, 3, 5, 10)


def sin_acentos(texto):
    nfkd = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def clave(titulo):
    """Comparación tolerante: 'Back To Your Love' == «back to your love»."""
    return re.sub(r"[^a-z0-9 ]", " ", sin_acentos(titulo).lower()).strip()


def cargar_jsonl(ruta):
    registros = []
    with open(ruta, encoding="utf-8") as f:
        for numero, linea in enumerate(f, 1):
            linea = linea.strip()
            if not linea:
                continue
            try:
                registros.append(json.loads(linea))
            except json.JSONDecodeError as exc:
                print(f"⚠️ {os.path.basename(ruta)}:{numero} ilegible ({exc})")
    return registros


def cargar(logs_dir):
    eventos, etiquetas = {}, []
    for ruta in sorted(glob.glob(os.path.join(logs_dir, "events_*.jsonl"))):
        for ev in cargar_jsonl(ruta):
            if ev.get("id"):
                eventos[ev["id"]] = ev
    for ruta in sorted(glob.glob(os.path.join(logs_dir, "feedback_*.jsonl"))):
        etiquetas.extend(cargar_jsonl(ruta))
    return eventos, etiquetas


def relevantes(evento, etiqueta, estricto):
    """Posiciones (1-based) que cuentan como relevantes para esta etiqueta."""
    ranking = evento.get("ranking") or []
    if etiqueta["valor"] != "gust":
        return set()
    if estricto:
        # Solo la canción que el usuario destacó; si no está en el ranking del
        # turno (feedback de un turno ya purgado) no se inventa relevancia.
        clave_ok = clave(etiqueta.get("track_name"))
        if not clave_ok:
            return set()
        return {c["rank"] for c in ranking if clave(c.get("track_name")) == clave_ok}
    # Cota amplia: el usuario aceptó la tanda completa.
    return {c["rank"] for c in ranking}


def metricas_etiquetados(eventos, etiquetas, estricto):
    """HR@K / Recall@K / Precision@K / MRR / NDCG@K sobre los turnos etiquetados.

    Cada etiqueta pesa lo mismo (un turno = una muestra), sea gust o no_gust:
    los turnos rechazados entran al denominador con 0 aciertos. Así el número
    no se infla contando solo los que gustaron.
    """
    recuentos = Counter()
    acumulados = {k: 0.0 for k in Ks}
    recall = {k: 0.0 for k in Ks}
    ndcg = {k: 0.0 for k in Ks}
    suma_rr = 0.0
    posicion_de_acierto = []   # rank en el que apareció la canción aceptada

    for etiqueta in etiquetas:
        evento = eventos.get(etiqueta.get("evento_id"))
        if evento is None:
            recuentos["etiquetas_sin_evento"] += 1
            continue
        recuentos["turnos_etiquetados"] += 1
        rel = relevantes(evento, etiqueta, estricto)
        ranking = sorted(evento.get("ranking") or [], key=lambda c: c.get("rank", 999))
        if rel:
            posicion_de_acierto.append(min(rel))
            suma_rr += 1 / min(rel)
            recuentos["con_relevante"] += 1
        elif etiqueta["valor"] == "gust":
            recuentos["gust_sin_coincidencia"] += 1
        for k in Ks:
            top_k = [c for c in ranking if c.get("rank", 999) <= k]
            aciertos = sum(1 for c in top_k if c.get("rank") in rel)
            if aciertos:
                recuentos[f"hit@{k}"] += 1
            acumulados[k] += aciertos / max(len(top_k), 1)
            if rel:
                recall[k] += aciertos / len(rel)
            dcg = sum(1 / math.log2(c["rank"] + 1) for c in top_k if c.get("rank") in rel)
            idcg = sum(1 / math.log2(i + 2) for i in range(min(len(rel), k)))
            ndcg[k] += (dcg / idcg) if idcg else 0.0

    total = recuentos["turnos_etiquetados"]
    if not total:
        return None
    con_relevante = recuentos["con_relevante"]
    salida = {"modo": "estricto" if estricto else "amplio", "turnos_etiquetados": total}
    for k in Ks:
        salida[f"hit_rate@{k}"] = round(recuentos[f"hit@{k}"] / total, 4)
        salida[f"recall@{k}"] = round(recall[k] / con_relevante, 4) if con_relevante else None
        salida[f"precision@{k}"] = round(acumulados[k] / total, 4)
        salida[f"ndcg@{k}"] = round(ndcg[k] / total, 4)
    salida["mrr"] = round(suma_rr / total, 4)
    salida["posicion_media_de_acierto"] = (
        round(sum(posicion_de_acierto) / len(posicion_de_acierto), 2)
        if posicion_de_acierto
        else None
    )
    salida["gust_sin_cancion_en_el_ranking"] = recuentos["gust_sin_coincidencia"]
    salida["etiquetas_sin_evento"] = recuentos["etiquetas_sin_evento"]
    return salida


def alineacion(eventos):
    """Coherencia con lo pedido: métrica objetiva que NO necesita etiquetas.

    El retrieval guarda por candidata `cumple_genero` (el género pedido está en
    sus etiquetas canónicas) y `desvio_animo` (distancia 0-1 al cuantil de ánimo
    pedido). Con eso la tesis puede medir alineación sobre TODOS los turnos, no
    solo sobre los etiquetados con 👍/👎.
    """
    plano = [(c, e) for e in eventos.values() for c in (e.get("ranking") or [])]
    genero = [c for c, _ in plano if c.get("cumple_genero") is not None]
    animo = [c.get("desvio_animo") for c, _ in plano if c.get("desvio_animo") is not None]
    top3 = [c for c, e in plano if c.get("cumple_genero") is not None and (c.get("rank") or 99) <= 3]
    turnos_con_genero = {id(e) for c, e in plano if c.get("cumple_genero") is not None}
    turnos_con_animo = {id(e) for c, e in plano if c.get("desvio_animo") is not None}
    return {
        "turnos_con_genero_pedido": len(turnos_con_genero),
        "coherencia_de_genero": (
            round(sum(1 for c in genero if c["cumple_genero"]) / len(genero), 4) if genero else None
        ),
        "coherencia_de_genero_top3": (
            round(sum(1 for c in top3 if c["cumple_genero"]) / len(top3), 4) if top3 else None
        ),
        "turnos_con_animo_pedido": len(turnos_con_animo),
        "desvio_de_animo_promedio": round(sum(animo) / len(animo), 4) if animo else None,
    }


def telemetria(eventos):
    """Diagnóstico del pipeline: se reporta aparte porque no es accuracy."""
    if not eventos:
        return {}
    coberturas = [((e.get("calidad") or {}).get("cobertura_m3") or 0) for e in eventos.values()]
    perfiles = sum(1 for e in eventos.values() if (e.get("calidad") or {}).get("perfil"))
    rechazadas = sum(1 for e in eventos.values() if (e.get("calidad") or {}).get("llm_rechazado"))
    latencias = sorted((e.get("latencies_ms") or {}).get("total", 0) for e in eventos.values())
    intentos = Counter((e.get("calidad") or {}).get("intencion", "?") for e in eventos.values())
    tipos = Counter((e.get("calidad") or {}).get("tipo_turno", "?") for e in eventos.values())
    heredados = sum(1 for e in eventos.values() if (e.get("calidad") or {}).get("perfil_heredado"))
    # Etiquetas canónicas de la ficha, no `genre_lyr` suelto: esa columna dice
    # "blues" en canciones que el propio catálogo también marca como rock, y la
    # distribución salía falseada justo lo que el retrieval corrigió.
    generos = Counter(
        g
        for e in eventos.values()
        for c in (e.get("ranking") or [])
        for g in (c.get("generos") or ([c["genre"]] if c.get("genre") else []))
    )
    return {
        "turnos_registrados": len(eventos),
        "cobertura_m3_promedio": round(sum(coberturas) / len(coberturas), 4),
        "turnos_con_perfil_animo": perfiles,
        "turnos_de_continuacion": dict(tipos),
        "turnos_con_perfil_heredado": heredados,
        "respuestas_rechazadas_por_QA": rechazadas,
        "latencia_p50_ms": round(_percentil(latencias, 0.50), 1),
        "latencia_p90_ms": round(_percentil(latencias, 0.90), 1),
        "intenciones": dict(intentos),
        "generos_entregados": dict(generos.most_common(8)),
    }


def _percentil(ordenado, q):
    if not ordenado:
        return 0.0
    idx = min(len(ordenado) - 1, int(q * (len(ordenado) - 1)))
    return ordenado[idx]


def informe(texto_informe, datos):
    lineas = [
        "# EchoPulse AI — evaluación del ranking",
        "",
        f"Generado: {datos['generado']}",
        f"Eventos leídos: {datos['eventos_leidos']} · Etiquetas: {datos['etiquetas_leidas']}",
        "",
        "## Métricas de ranking (estricto: solo cuenta la canción destacada)",
    ]
    estricto = datos["estricto"]
    if not estricto:
        lineas.append("_Sin etiquetas: todavía no se puede calcular ninguna._")
    else:
        lineas.append(
            "| Métrica | " + " | ".join(f"@{k}" for k in Ks) + " |\n|---|" + "---|" * len(Ks)
        )
        for nombre in ("hit_rate", "recall", "precision", "ndcg"):
            celdas = []
            for k in Ks:
                v = estricto.get(f"{nombre}@{k}")
                celdas.append("–" if v is None else f"{v * 100:.1f}%")
            lineas.append(f"| {nombre.title().replace('_', ' ')} | " + " | ".join(celdas) + " |")
        lineas.append("")
        lineas.append(f"- MRR estricto: **{estricto['mrr']:.3f}**")
        lineas.append(
            f"- Turnos con al menos una canción aceptada dentro del top 10 y rank "
            f"promedio de esa canción: **{estricto['posicion_media_de_acierto']}**"
        )
        lineas.append(
            f"- Etiquetas 'gust' cuyo candidato ya no estaba en el ranking: "
            f"**{estricto['gust_sin_cancion_en_el_ranking']}** · sin evento: "
            f"**{estricto['etiquetas_sin_evento']}**"
        )
        amplio = datos["amplio"]
        if amplio:
            lineas.append("")
            lineas.append(
                "## Cota superior (amplio: la tanda aceptada cuenta como 10 relevantes)"
            )
            lineas.append(
                "- "
                + " · ".join(
                    f"HR@{k} {round(amplio.get(f'hit_rate@{k}', 0) * 100, 1)}%" for k in (1, 5, 10)
                )
                + f" · MRR {amplio['mrr']:.3f}"
            )
    lineas += [
        "",
        "## Alineación con lo pedido (no necesita etiquetas)",
        "```json",
        json.dumps(datos["alineacion"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Telemetría del pipeline (no es accuracy)",
        "```json",
        json.dumps(datos["telemetria"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Cómo leerlo",
        "- Las métricas de ranking solo valen sobre turnos **etiquetados**; con pocas "
        "muestras el intervalo de confianza es enorme: reportar el conteo junto al porcentaje.",
        "- Las etiquetas cuyo evento ya no está en los logs se descartan (no hay con "
        "qué cruzarlas) y se reportan aparte: reducen la muestra, no la media.",
        "- Un 'gust' sin canción localizable en ese ranking cuenta como fallo: aporta 0 "
        "a HR, Precision, NDCG y MRR.",
        "- La cota amplia infla a propósito: sirve para acotar, no como resultado.",
        "- Hit Rate aquí mide 'la canción aceptada aparece en el top-K', con el ranking "
        "máximo de 10 que entrega el agente; Recall@10 coincide con HR@10 por construcción.",
        "- Alineación es un proxy del retrieval (¿devuelve lo que se le pidió?), medible "
        "en todos los turnos; satisfacción es lo que miden HR/MRR sobre los etiquetados.",
    ]
    texto_informe.write("\n".join(lineas) + "\n")


def main():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description="Métricas de ranking de EchoPulse AI")
    parser.add_argument("--logs", default=os.path.join(raiz, "logs"))
    parser.add_argument("--md", default=os.path.join(raiz, "logs", "informe_evaluacion.md"))
    parser.add_argument("--json", dest="json_out", default=os.path.join(raiz, "logs", "informe_evaluacion.json"))
    args = parser.parse_args()

    eventos, etiquetas = cargar(args.logs)
    if not eventos:
        print(f"❌ No hay logs/events_*.jsonl en {args.logs}: nada que evaluar.")
        return 1

    from datetime import datetime

    datos = {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "eventos_leidos": len(eventos),
        "etiquetas_leidas": len(etiquetas),
        "estricto": metricas_etiquetados(eventos, etiquetas, estricto=True),
        "telemetria": telemetria(eventos),
        "alineacion": alineacion(eventos),
    }
    datos["amplio"] = metricas_etiquetados(eventos, etiquetas, estricto=False)

    with open(args.json_out, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
    with open(args.md, "w", encoding="utf-8") as f:
        informe(f, datos)

    print(f"📄 {args.md}\n🧾 {args.json_out}")
    e = datos["estricto"]
    if not e:
        print("⚠️ 0 etiquetas: pide a quien pruebe la demo que pulse 👍/👎 en cada tanda.")
    else:
        print(
            f"✅ turnos etiquetados {e['turnos_etiquetados']} | "
            + " | ".join(f"HR@{k} {e[f'hit_rate@{k}'] * 100:.1f}%" for k in Ks)
            + f" | MRR {e['mrr']:.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
