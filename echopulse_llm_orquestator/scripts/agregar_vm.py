# agregar_vm.py — Telemetría de la demo a nivel de TURNOS y SESIONES
"""
Resume los eventos que registró el agente desplegado. La unidad de análisis es
el turno de conversación (y la sesión que lo agrupa), no la persona: el registro
no permite atribuir un turno a un visitante humano concreto, así que todas las
métricas de plataforma se reportan sobre el total de turnos atendidos.

Corre DENTRO del contenedor de la app (donde viven /app/logs):
    python /tmp/agregar_vm.py --salida /tmp/vm_agg.json
No importa torch ni carga modelos: solo lee los JSONL.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import statistics as st
from datetime import datetime
from pathlib import Path


def percentiles(vals, ps=(50, 90, 99)):
    if not vals:
        return {p: 0.0 for p in ps}
    v = sorted(vals)
    out = {}
    for p in ps:
        k = (len(v) - 1) * p / 100.0
        a, b = int(k), min(int(k) + 1, len(v) - 1)
        out[p] = round(v[a] + (v[b] - v[a]) * (k - a), 1)
    return out


def resumen(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"n": 0, "prom": 0.0, "p50": 0.0, "p90": 0.0, "p99": 0.0}
    return {"n": len(vals), "prom": round(st.mean(vals), 1), **percentiles(vals)}


def leer(pattern):
    filas = []
    for ruta in sorted(glob.glob(pattern)):
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    filas.append(json.loads(linea))
                except json.JSONDecodeError:
                    pass
    return filas


def banda(tarjetas, corte):
    if not tarjetas:
        return {"n": 0, "emergentes_pct": 0.0, "popularity": 0.0, "similarity": 0.0,
                "desvio_animo": 0.0, "cumple_genero_pct": 0.0}
    eme = sum(1 for t in tarjetas if t.get("emergente"))
    pops = [t["popularity"] for t in tarjetas if isinstance(t.get("popularity"), (int, float))]
    sims = [t["similarity"] for t in tarjetas if isinstance(t.get("similarity"), (int, float))]
    desv = [t["desvio_animo"] for t in tarjetas if isinstance(t.get("desvio_animo"), (int, float))]
    cg = [t["cumple_genero"] for t in tarjetas if t.get("cumple_genero") is not None]
    return {
        "n": len(tarjetas),
        "emergentes_pct": round(100.0 * eme / len(tarjetas), 2),
        "popularity": round(st.mean(pops), 2) if pops else 0.0,
        "similarity": round(st.mean(sims), 4) if sims else 0.0,
        "desvio_animo": round(st.mean(desv), 4) if desv else 0.0,
        "cumple_genero_pct": round(100.0 * sum(1 for v in cg if v) / len(cg), 2) if cg else None,
    }


def agregar(logs_dir):
    eventos = [e for e in leer(str(Path(logs_dir) / "events_*.jsonl")) if e.get("ranking")]
    eventos.sort(key=lambda e: e.get("timestamp") or "")
    metricas = leer(str(Path(logs_dir) / "metrics_*.jsonl"))
    feedback = leer(str(Path(logs_dir) / "feedback_*.jsonl"))

    sesiones = collections.defaultdict(list)
    for e in eventos:
        sesiones[e.get("session_id") or "sin-sesion"].append(e)

    lat_total, etapas = [], collections.defaultdict(list)
    voz = collections.Counter()
    rechazos = 0
    cobertura, sin_clase, intencion = [], 0, collections.Counter()
    artistas, emergentes, reconocidos, repetidas, sin_nombre = [], [], [], 0, 0
    hits = misses = 0
    todas, visibles, internas = [], [], []
    generos = collections.Counter()
    tipos = collections.Counter()
    perfiles = collections.Counter()
    consultas = collections.Counter()
    minuto = collections.Counter()
    fallos = 0

    for e in eventos:
        c = e.get("calidad") or {}
        lat = e.get("latencies_ms") or {}
        if lat.get("total") is not None:
            lat_total.append(lat["total"])
        for nombre, valor in lat.items():
            etapas[nombre].append(valor)
        proveedor = c.get("llm_proveedor") or "determinista"
        voz[proveedor] += 1
        if c.get("llm_rechazado"):
            rechazos += 1
        if "cobertura_m3" in c:
            cobertura.append(c["cobertura_m3"])
            if not c["cobertura_m3"]:
                sin_clase += 1
        intencion[c.get("intencion") or "desconocida"] += 1
        if "artistas_distintos" in c:
            artistas.append(c["artistas_distintos"])
        emergentes.append(c.get("emergentes", 0))
        reconocidos.append(c.get("reconocidos", 0))
        repetidas += c.get("repetidas", 0)
        sin_nombre += c.get("sin_nombre", 0)
        hits += c.get("metadata_hits", 0)
        misses += c.get("metadata_misses", 0)
        tipos[e.get("tipo_turno") or c.get("tipo_turno") or "desconocido"] += 1
        perfiles[c.get("perfil") or "sin perfil"] += 1
        consultas[(e.get("query_en") or "")[:60]] += 1
        tarjetas = e["ranking"]
        todas.extend(tarjetas)
        visibles.extend(tarjetas[:3])
        internas.extend(tarjetas[3:10])
        for t in tarjetas:
            g = t.get("genre")
            if g:
                generos[str(g)] += 1
        marca = (e.get("timestamp") or "")[:16]
        if marca:
            minuto[marca] += 1
        if not e.get("respuesta"):
            fallos += 1

    por_sesion = []
    for sid, lista in sesiones.items():
        ls = [(x.get("latencies_ms") or {}).get("total") for x in lista]
        ls = [v for v in ls if v is not None]
        por_sesion.append({
            "sesion": sid[:8],
            "turnos": len(lista),
            "desde": lista[0].get("timestamp"),
            "hasta": lista[-1].get("timestamp"),
            "lat_prom": round(st.mean(ls), 1) if ls else 0.0,
            "deterministas": sum(1 for x in lista
                                 if (x.get("calidad") or {}).get("llm_proveedor") == "determinista"),
        })
    por_sesion.sort(key=lambda s: s["desde"] or "")

    n = len(eventos)
    return {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "fuente": str(logs_dir),
        "turnos": n,
        "sesiones": len(sesiones),
        "desde": eventos[0].get("timestamp") if eventos else None,
        "hasta": eventos[-1].get("timestamp") if eventos else None,
        "turnos_por_sesion": {
            "prom": round(n / len(sesiones), 2) if sesiones else 0,
            "max": max((s["turnos"] for s in por_sesion), default=0),
            "dist": dict(collections.Counter(s["turnos"] for s in por_sesion)),
        },
        "latencia_ms": resumen(lat_total),
        "latencias_total": [round(v, 1) for v in lat_total],
        "etapas_ms": {k: resumen(v) for k, v in sorted(etapas.items())},
        "voz": {
            "llm": voz.get("custom", 0) + voz.get("ollama", 0) + voz.get("hf", 0),
            "determinista": voz.get("determinista", 0),
            "por_proveedor": dict(voz),
            "rechazos": rechazos,
            "tasa_rechazo_pct": round(100.0 * rechazos / n, 2) if n else 0.0,
        },
        "intencion": {
            "por_fuente": dict(intencion),
            "cobertura_m3_prom_pct": round(100.0 * st.mean(cobertura), 2) if cobertura else 0.0,
            "turnos_sin_clase": sin_clase,
            "hist": [round(100.0 * v, 1) for v in cobertura],
        },
        "diversidad": {
            "artistas_distintos_prom": round(st.mean(artistas), 2) if artistas else 0.0,
            "emergentes_prom": round(st.mean(emergentes), 2) if emergentes else 0.0,
            "reconocidos_prom": round(st.mean(reconocidos), 2) if reconocidos else 0.0,
            "repetidas": repetidas,
            "sin_nombre": sin_nombre,
            "metadata_pct": round(100.0 * hits / (hits + misses), 2) if (hits + misses) else 0.0,
        },
        "tarjetas": banda(todas, 10),
        "bandas": {"visible 1-3": banda(visibles, 3), "interno 4-10": banda(internas, 7)},
        "generos_top": generos.most_common(12),
        "tipos_turno": dict(tipos),
        "perfiles_top": perfiles.most_common(10),
        "consultas_top": consultas.most_common(15),
        "ritmo": {
            "por_minuto": sorted(minuto.items()),
            "rpm_pico": max(minuto.values()) if minuto else 0,
            "rpm_prom": round(st.mean(list(minuto.values())), 2) if minuto else 0,
            "minutos_activos": len(minuto),
        },
        "feedback": {
            "total": len(feedback),
            "por_valor": dict(collections.Counter(f.get("valor") for f in feedback)),
        },
        "metricas_registros": len(metricas),
        "turnos_sin_respuesta": fallos,
        "por_sesion": por_sesion,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--logs", default="/app/logs")
    p.add_argument("--salida", default="/tmp/vm_agg.json")
    args = p.parse_args()
    datos = agregar(args.logs)
    Path(args.salida).write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    print(f"turnos={datos['turnos']} sesiones={datos['sesiones']} "
          f"p50={datos['latencia_ms']['p50']}ms deterministas={datos['voz']['determinista']} "
          f"rechazo={datos['voz']['tasa_rechazo_pct']}%")
    print(f"salida={args.salida} bytes={Path(args.salida).stat().st_size}")


if __name__ == "__main__":
    main()
