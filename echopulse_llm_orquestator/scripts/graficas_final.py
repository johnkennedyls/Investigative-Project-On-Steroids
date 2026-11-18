# scripts/graficas_final.py - Figuras del informe final, todas con datos medidos
"""Consolida la evidencia experimental y produce las figuras del Anexo 3.

Fuentes, en orden de lectura:
  build/eva/turnos_*.jsonl   turnos de la demo desplegada (ranking completo)
  build/eva/resumen_*.json   agregado de operación de esa corrida
  build/eva/ranking.json     HR@1 / Recall@10 / MRR / NDCG@10 y líneas base
  docs/resultados encuesta.xlsx  instrumento cualitativo de 20 ítems
  docs/Tabla_Maestra_Transformer.ipynb   curva de pérdida real del entrenamiento
  docs/TalkplayTransformer_Intentional.ipynb  validación del módulo de intención

Ninguna cifra se escribe a mano: si un insumo falta, la figura correspondiente se
omite y el informe lo declara. La salida `datos_informe.json` es el único insumo
del constructor del documento.

    python scripts/graficas_final.py
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import statistics as st
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from informe_evaluacion import analizar_encuesta  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
EVA = RAIZ / "build" / "eva"
ASSETS = RAIZ / "docs" / "informe_final_assets"

AZUL = "#1D4ED8"
VERDE = "#0F766E"
AMBAR = "#B45309"
ROJO = "#B42318"
GRIS = "#64748B"
LILA = "#6D28D9"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9.5,
    "axes.titlesize": 11.5, "axes.titleweight": "bold", "axes.labelsize": 9.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.28, "grid.linewidth": 0.6,
    "figure.dpi": 160, "savefig.dpi": 160, "savefig.bbox": "tight",
    "legend.frameon": False, "legend.fontsize": 8.5,
})

METRICAS = (("hr1", "HR@1"), ("recall10", "Recall@10"),
            ("rr", "MRR"), ("ndcg10", "NDCG@10"))
METODOS = (("sistema", "EchoPulse (10 tarjetas)", AZUL),
           ("sistema_visible", "EchoPulse (3 visibles)", VERDE),
           ("popularidad", "Popularidad global", AMBAR),
           ("lexica", "Jaccard léxico", LILA),
           ("aleatorio", "Aleatorio", GRIS))


def _ultimo(patron: str) -> str | None:
    rutas = sorted(glob.glob(str(EVA / patron)))
    return rutas[-1] if rutas else None


def leer_turnos() -> list[dict]:
    eventos = []
    for ruta in sorted(glob.glob(str(EVA / "turnos_*.jsonl"))):
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
    eventos.sort(key=lambda e: e.get("timestamp") or "")
    return eventos


def leer_notebooks() -> dict:
    """Extrae la curva de pérdida y la validación de intención tal como quedaron
    registradas en las salidas de los notebooks (no se reejecuta nada)."""
    salida: dict = {}
    ruta = RAIZ / "docs" / "Tabla_Maestra_Transformer.ipynb"
    if ruta.exists():
        nb = json.loads(ruta.read_text(encoding="utf-8"))
        for c in nb["cells"]:
            src = "".join(c.get("source", []))
            m = re.search(r"loss_vals\s*=\s*\[([^\]]+)\]", src)
            if m:
                salida["perdida"] = [float(x) for x in m.group(1).split(",")]
            for o in c.get("outputs", []):
                txt = "".join(o.get("text", []))
                v = re.search(r"Vocabulario:\s*(\d+)", txt)
                if v:
                    salida["vocabulario"] = int(v.group(1))
                e = re.search(r"ÉPOCA (\d+) FINALIZADA", txt)
                if e:
                    salida["epocas"] = max(salida.get("epocas", 0), int(e.group(1)))
                d = re.search(r"Entrenando en (\w+)", txt)
                if d:
                    salida["dispositivo_entrenamiento"] = d.group(1)
    ruta = RAIZ / "docs" / "TalkplayTransformer_Intentional.ipynb"
    if ruta.exists():
        nb = json.loads(ruta.read_text(encoding="utf-8"))
        for c in nb["cells"]:
            for o in c.get("outputs", []):
                txt = "".join(o.get("text", []))
                for clave, patron in (("mrr", r"Mean Reciprocal Rank \(MRR\):\s*([\d.]+)"),
                                      ("hr1", r"Hit Rate @1:\s*([\d.]+)%"),
                                      ("hr5", r"Hit Rate @5:\s*([\d.]+)%"),
                                      ("hr10", r"Hit Rate @10:\s*([\d.]+)%")):
                    m = re.search(patron, txt)
                    if m:
                        salida.setdefault("intencion", {})[clave] = float(m.group(1))
                m = re.search(r"Evaluando (\d+) muestras en (\w+)", txt)
                if m:
                    salida.setdefault("intencion", {})["muestras"] = int(m.group(1))
                    salida["intencion"]["dispositivo_validacion"] = m.group(2)
                m = re.search(r"Entrenando con (\d+) posibles canciones", txt)
                if m:
                    salida.setdefault("intencion", {})["clases"] = int(m.group(1))
                m = re.search(r"(\d+)/(\d+) \[([\d:]+)<", txt)
                if m:
                    salida.setdefault("intencion", {})["velocidad_it_s"] = None
                m = re.search(r"([\d.]+)it/s\]", txt)
                if m:
                    salida.setdefault("intencion", {})["velocidad_it_s"] = float(m.group(1))
    # La curva de pérdida tiene una entrada por época: es el conteo fiable cuando
    # los outputs del notebook solo conservan el aviso de la primera época.
    if len(salida.get("perdida") or []) > 1:
        salida["epocas"] = len(salida["perdida"])
    return salida


def agregar_turnos(eventos: list[dict]) -> dict:
    """Estadística de operación a nivel de TURNO y de SESIÓN (no de visitante)."""
    if not eventos:
        return {}
    tarjetas = [c for e in eventos for c in e["ranking"]]
    visibles = [c for e in eventos for c in e["ranking"][:int(e.get("destacadas") or 3)]]
    tarjetas_con_genero = [c for e in eventos
                           if "genre=" in str((e["calidad"].get("perfil") or ""))
                           for c in e["ranking"]]
    lat_cliente = [e["ms_cliente"] for e in eventos if e.get("ms_cliente")]
    lat_serv = [(e.get("latencies_ms") or {}).get("total") for e in eventos]
    lat_serv = [x for x in lat_serv if x]
    etapas: dict[str, list[float]] = {}
    for e in eventos:
        for k, v in (e.get("latencies_ms") or {}).items():
            if isinstance(v, (int, float)):
                etapas.setdefault(k, []).append(float(v))
    por_sesion: dict[str, list[dict]] = {}
    for e in eventos:
        por_sesion.setdefault(e["session_id"], []).append(e)
    desvios = [c["desvio_animo"] for c in tarjetas if c.get("desvio_animo") is not None]
    proveedores = Counter((e["calidad"].get("llm_proveedor") or "sin dato") for e in eventos)
    fuentes = Counter((e["calidad"].get("intencion") or "sin dato") for e in eventos)
    tipos = Counter((e.get("tipo_turno") or "sin dato") for e in eventos)
    perfiles = Counter((e["calidad"].get("perfil") or "sin perfil") for e in eventos)
    generos = Counter(g for c in tarjetas for g in (c.get("generos") or []))
    consultas = Counter((e.get("query_en") or "")[:70] for e in eventos)
    marcas = sorted(e["timestamp"] for e in eventos if e.get("timestamp"))
    minutos = Counter(m[:16] for m in marcas)
    repetidas = 0
    for sesion, lista in por_sesion.items():
        vistos: set[str] = set()
        for e in sorted(lista, key=lambda x: x.get("turno") or 0):
            for c in e["ranking"][:int(e.get("destacadas") or 3)]:
                clave = str(c.get("id") or f"{c.get('artist_name')}|{c.get('track_name')}")
                if clave in vistos:
                    repetidas += 1
                vistos.add(clave)
    cobertura = [e["calidad"].get("cobertura_m3") for e in eventos]
    cobertura = [c for c in cobertura if isinstance(c, (int, float))]
    metadata = [e["calidad"].get("metadata_coverage") for e in eventos]
    metadata = [m for m in metadata if isinstance(m, (int, float))]

    def pct(vals, q):
        if not vals:
            return 0.0
        orden = sorted(vals)
        return round(orden[min(len(orden) - 1, max(0, int(round(q * (len(orden) - 1)))))], 1)

    return {
        "turnos": len(eventos),
        "sesiones": len(por_sesion),
        "desde": marcas[0] if marcas else None,
        "hasta": marcas[-1] if marcas else None,
        "turnos_por_sesion": {
            "promedio": round(st.mean(len(v) for v in por_sesion.values()), 2),
            "maximo": max(len(v) for v in por_sesion.values()),
            "distribucion": dict(sorted(Counter(len(v) for v in por_sesion.values()).items())),
        },
        "latencia_cliente_ms": {"n": len(lat_cliente),
                                "promedio": round(st.mean(lat_cliente), 1) if lat_cliente else 0,
                                "p50": pct(lat_cliente, .5), "p90": pct(lat_cliente, .9),
                                "p99": pct(lat_cliente, .99),
                                "maximo": round(max(lat_cliente), 1) if lat_cliente else 0},
        "latencia_servidor_ms": {"n": len(lat_serv),
                                 "promedio": round(st.mean(lat_serv), 1) if lat_serv else 0,
                                 "p50": pct(lat_serv, .5), "p90": pct(lat_serv, .9),
                                 "p99": pct(lat_serv, .99)},
        "etapas_ms": {k: {"promedio": round(st.mean(v), 1), "p90": pct(v, .9), "n": len(v)}
                      for k, v in sorted(etapas.items())},
        "tarjetas_internas": len(tarjetas),
        "tarjetas_visibles": len(visibles),
        "voz": {"por_proveedor": dict(proveedores.most_common()),
                "llm": sum(v for k, v in proveedores.items() if k not in ("determinista", "sin dato")),
                "determinista": proveedores.get("determinista", 0),
                "rechazos": sum(1 for e in eventos if e["calidad"].get("llm_rechazado")),
                "tasa_rechazo_pct": round(100 * sum(1 for e in eventos
                                                    if e["calidad"].get("llm_rechazado")) / len(eventos), 1)},
        "intencion": {"por_fuente": dict(fuentes.most_common()),
                      "cobertura_m3_prom_pct": round(100 * st.mean(cobertura), 1) if cobertura else 0,
                      "metadata_prom_pct": round(100 * st.mean(metadata), 1) if metadata else 0},
        "diversidad": {
            "emergentes_pct": round(100 * sum(1 for c in tarjetas if c.get("emergente")) / len(tarjetas), 1),
            "reconocidos_pct": round(100 * sum(1 for c in tarjetas if c.get("reconocido")) / len(tarjetas), 1),
            "emergentes_visibles_pct": round(100 * sum(1 for c in visibles if c.get("emergente")) / len(visibles), 1)
            if visibles else 0,
            "artistas_distintos_prom": round(st.mean(
                len({(c.get("artist_name") or "").lower() for c in e["ranking"]}) for e in eventos), 2),
            "artistas_distintos_visibles_prom": round(st.mean(
                len({(c.get("artist_name") or "").lower()
                     for c in e["ranking"][:int(e.get("destacadas") or 3)]}) for e in eventos), 2),
            "generos_distintos_prom": round(st.mean(
                len({g for c in e["ranking"] for g in (c.get("generos") or [])}) for e in eventos), 2),
            "repetidas_en_sesion": repetidas,
            "sin_nombre": sum(1 for c in tarjetas if not (c.get("track_name") or "").strip()),
        },
        "cumplimiento": {
            "genero_pct": round(100 * sum(1 for c in tarjetas if c.get("cumple_genero")) / len(tarjetas), 1),
            # Cumplimiento sobre las tarjetas de los turnos que pidieron género, que
            # es el denominador correcto: en un turno de solo ánimo no hay género
            # prometido que cumplir.
            "genero_pct_con_pedido": round(
                100 * sum(1 for c in tarjetas_con_genero if c.get("cumple_genero")) /
                max(1, len(tarjetas_con_genero)), 1),
            "tarjetas_con_genero": len(tarjetas_con_genero),
            "turnos_con_genero": sum(1 for e in eventos
                                     if "genre=" in str(((e.get("calidad") or {}).get("perfil") or ""))),
            "desvio_animo_prom": round(st.mean(desvios), 3) if desvios else None,
            "desvio_animo_p90": round(pct(desvios, .9), 3) if desvios else None,
            "desvio_animo_hist": [round(x, 3) for x in desvios],
            "turnos_con_perfil": sum(1 for e in eventos
                                     if (e["calidad"].get("perfil") or "sin perfil") != "sin perfil"),
            "perfil_heredado": sum(1 for e in eventos if e["calidad"].get("perfil_heredado")),
        },
        "tipos_turno": dict(tipos.most_common()),
        "perfiles_top": dict(perfiles.most_common(12)),
        "consultas_top": dict(consultas.most_common(10)),
        "generos_top": dict(generos.most_common(10)),
        "ritmo": {"por_minuto": dict(sorted(minutos.items())),
                  "rpm_prom": round(st.mean(minutos.values()), 2) if minutos else 0,
                  "rpm_pico": max(minutos.values()) if minutos else 0,
                  "minutos_activos": len(minutos)},
        "por_sesion": [{"sesion": s[:24], "turnos": len(v),
                        "latencia_prom_ms": round(st.mean(
                            [x["ms_cliente"] for x in v if x.get("ms_cliente")] or [0]), 1)}
                       for s, v in sorted(por_sesion.items())],
    }


# ------------------------------------------------------------------ figuras --

def g_convergencia(d, ruta):
    p = d.get("notebooks", {}).get("perdida")
    if not p:
        return False
    ep = list(range(1, len(p) + 1))
    fig, ax = plt.subplots(figsize=(8.6, 3.5))
    ax.plot(ep, p, marker="o", color=AZUL, linewidth=2, markersize=4.5)
    ax.set_yscale("log")
    ax.set_xlabel("Época")
    ax.set_ylabel("Pérdida MSE (escala log)")
    ax.set_title("Convergencia del Transformer de contenido (Tabla Maestra)")
    ax.set_xticks(ep)
    ax.annotate(f"{p[0]:.4f}", (ep[0], p[0]), textcoords="offset points",
                xytext=(6, 8), fontsize=8.5, color=GRIS)
    ax.annotate(f"{p[-1]:.4f}", (ep[-1], p[-1]), textcoords="offset points",
                xytext=(-30, 10), fontsize=8.5, color=VERDE)
    fig.savefig(ruta)
    plt.close(fig)
    return True


def g_ranking(d, ruta):
    r = (d.get("ranking") or {}).get("agregado_gradado") or (d.get("ranking") or {}).get("agregado")
    if not r:
        return False
    presentes = [(k, et, c) for k, et, c in METODOS if r.get(k)]
    x = np.arange(len(METRICAS))
    ancho = 0.8 / len(presentes)
    fig, ax = plt.subplots(figsize=(9.2, 3.9))
    for i, (k, et, c) in enumerate(presentes):
        vals = [r[k].get(m, 0) for m, _ in METRICAS]
        pos = x + (i - (len(presentes) - 1) / 2) * ancho
        ax.bar(pos, vals, ancho * 0.92, label=et, color=c)
        for px, v in zip(pos, vals):
            ax.text(px, v + 0.012, f"{v:.2f}", ha="center", fontsize=7.4, color=GRIS)
    ax.set_xticks(x)
    ax.set_xticklabels([et for _, et in METRICAS])
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Valor [0, 1]")
    ax.set_title("Precisión de orden frente a tres líneas base (relevancia gradada)")
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.14))
    fig.savefig(ruta)
    plt.close(fig)
    return True


def g_latencia(d, ruta):
    t = d.get("turnos") or {}
    etapas = t.get("etapas_ms") or {}
    if not etapas:
        return False
    orden = [k for k in ("translation", "retrieval_m2", "reranking_m3", "generation", "total")
             if k in etapas] or list(etapas)
    etiquetas = {"translation": "Traducción\n(ES→EN)", "retrieval_m2": "Retrieval\nMódulo 2",
                 "reranking_m3": "Re-ranking\nMódulo 3", "generation": "Generación\nde voz",
                 "total": "Turno\ncompleto"}
    prom = [etapas[k]["promedio"] for k in orden]
    p90 = [etapas[k]["p90"] for k in orden]
    x = np.arange(len(orden))
    fig, ax = plt.subplots(figsize=(8.8, 3.6))
    ax.bar(x - 0.19, prom, 0.38, label="Promedio", color=AZUL)
    ax.bar(x + 0.19, p90, 0.38, label="Percentil 90", color=AMBAR)
    for px, v in zip(x - 0.19, prom):
        ax.text(px, v + max(prom) * 0.02, f"{v:,.0f}", ha="center", fontsize=7.6, color=GRIS)
    ax.set_xticks(x)
    ax.set_xticklabels([etiquetas.get(k, k) for k in orden])
    ax.set_ylabel("Milisegundos")
    ax.set_title("Latencia por etapa del turno en la demo desplegada")
    ax.legend()
    fig.savefig(ruta)
    plt.close(fig)
    return True


def g_percentiles(d, ruta):
    t = d.get("turnos") or {}
    cli, serv = t.get("latencia_cliente_ms") or {}, t.get("latencia_servidor_ms") or {}
    if not cli:
        return False
    etiquetas = ["Promedio", "p50", "p90", "p99"]
    claves = ["promedio", "p50", "p90", "p99"]
    x = np.arange(4)
    fig, ax = plt.subplots(figsize=(7.6, 3.4))
    ax.bar(x - 0.19, [cli.get(k, 0) for k in claves], 0.38, label="Cliente (extremo a extremo)", color=AZUL)
    ax.bar(x + 0.19, [serv.get(k, 0) for k in claves], 0.38, label="Servidor (procesamiento)", color=VERDE)
    for px, k in zip(x - 0.19, claves):
        ax.text(px, cli.get(k, 0) * 1.02, f"{cli.get(k, 0):,.0f}", ha="center", fontsize=7.6, color=GRIS)
    ax.set_xticks(x)
    ax.set_xticklabels(etiquetas)
    ax.set_ylabel("Milisegundos")
    ax.set_title("Distribución de la latencia por turno")
    ax.legend()
    fig.savefig(ruta)
    plt.close(fig)
    return True


def g_diversidad(d, ruta):
    div = (d.get("turnos") or {}).get("diversidad") or {}
    if not div:
        return False
    fig, ejes = plt.subplots(1, 2, figsize=(9.2, 3.5))
    ax = ejes[0]
    etiquetas = ["Artistas emergentes", "Artistas reconocidos"]
    vals = [div.get("emergentes_pct", 0), div.get("reconocidos_pct", 0)]
    ax.barh(etiquetas, vals, color=[VERDE, AMBAR], height=0.5)
    for i, v in enumerate(vals):
        ax.text(v + 1, i, f"{v:.1f} %", va="center", fontsize=9, color=GRIS)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Porcentaje de las tarjetas internas")
    ax.set_title("Mezcla de catálogo")
    ax = ejes[1]
    datos = [div.get("artistas_distintos_prom", 0), div.get("artistas_distintos_visibles_prom", 0),
             div.get("generos_distintos_prom", 0)]
    ax.bar(["Artistas distintos\n(10 internas)", "Artistas distintos\n(3 visibles)",
            "Géneros distintos\npor tanda"], datos, color=[AZUL, VERDE, LILA], width=0.55)
    for i, v in enumerate(datos):
        ax.text(i, v + 0.12, f"{v:.2f}", ha="center", fontsize=9, color=GRIS)
    ax.set_ylabel("Promedio por turno")
    ax.set_title("Diversidad intra-lista")
    fig.tight_layout()
    fig.savefig(ruta)
    plt.close(fig)
    return True


def g_cumplimiento(d, ruta):
    c = (d.get("turnos") or {}).get("cumplimiento") or {}
    hist = c.get("desvio_animo_hist") or []
    if not hist:
        return False
    fig, ejes = plt.subplots(1, 2, figsize=(9.2, 3.4), gridspec_kw={"width_ratios": [1, 1.5]})
    ax = ejes[0]
    pct = c.get("genero_pct_con_pedido") if c.get("genero_pct_con_pedido") is not None else c.get("genero_pct", 0)
    ax.bar(["Cumple el\ngénero pedido"], [pct], color=VERDE, width=0.4)
    ax.text(0, pct + 1.5, f"{pct:.1f} %", ha="center", fontsize=10, color=GRIS)
    ax.set_ylim(0, 108)
    ax.set_ylabel("Porcentaje de tarjetas")
    ax.set_title("Coherencia de género")
    ax = ejes[1]
    ax.hist(hist, bins=30, color=AZUL, edgecolor="white", linewidth=0.4)
    ax.axvline(0.25, color=ROJO, linestyle="--", linewidth=1.3, label="Umbral de relevancia (0,25)")
    ax.set_xlabel("Desvío de ánimo frente al perfil pedido (cuantiles)")
    ax.set_ylabel("Tarjetas")
    ax.set_title(f"Desvío de ánimo · media {c.get('desvio_animo_prom', 0):.3f}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(ruta)
    plt.close(fig)
    return True


def g_sensibilidad(d, ruta):
    s = (d.get("ranking") or {}).get("sensibilidad") or {}
    principal = (d.get("ranking") or {}).get("agregado_gradado") or {}
    if not s or not principal:
        return False
    umbrales = sorted(s, key=float)
    etiquetas = [f"{float(u):.2f}" for u in umbrales]
    fig, ejes = plt.subplots(1, 2, figsize=(9.2, 3.4))
    for ax, (clave, titulo) in zip(ejes, (("ndcg10", "NDCG@10"), ("hr1", "HR@1"))):
        for k, et, c in METODOS:
            if k == "sistema_visible":
                continue
            vals = [s[u].get(k, {}).get(clave, 0) for u in umbrales]
            if k == "sistema" and principal.get(k):
                vals = vals + [principal[k].get(clave, 0)]
            xs = list(range(len(vals)))
            ax.plot(xs, vals, marker="o", color=c, label=et, linewidth=1.8, markersize=4)
        ax.set_xticks(range(len(etiquetas) + 1))
        ax.set_xticklabels(etiquetas + ["0,25\n(principal)"])
        ax.set_xlabel("Umbral de desvío de ánimo")
        ax.set_ylabel(titulo)
        ax.set_title(f"Sensibilidad · {titulo}")
        ax.set_ylim(-0.02, 1.02)
    ejes[0].legend(loc="lower left", fontsize=7.6)
    fig.tight_layout()
    fig.savefig(ruta)
    plt.close(fig)
    return True


def g_encuesta_bloques(d, ruta):
    e = d.get("encuesta") or {}
    bloques = e.get("bloques") or []
    if not bloques:
        return False
    nombres = [b["nombre"] for b in bloques]
    medias = [b["media"] for b in bloques]
    sds = [b["sd"] for b in bloques]
    y = np.arange(len(bloques))
    fig, ax = plt.subplots(figsize=(9.0, 3.6))
    ax.barh(y, medias, xerr=sds, capsize=4, color=AZUL, height=0.55,
            error_kw={"ecolor": GRIS, "linewidth": 1.1})
    for yi, m, s in zip(y, medias, sds):
        ax.text(m + s + 0.03, yi, f"{m:.3f} ± {s:.3f}", va="center", fontsize=8.6, color=GRIS)
    ax.axvline(e.get("media_global", 0), color=ROJO, linestyle="--", linewidth=1.2,
               label=f"Media global {e.get('media_global', 0):.3f}")
    ax.set_yticks(y)
    ax.set_yticklabels(nombres, fontsize=9)
    ax.invert_yaxis()
    # Eje recortado: las medias de los cinco bloques caen en una franja de 0,03,
    # así que con base en 0 las barras serían indistinguibles. El recorte se
    # declara en el rótulo del eje para no exagerar la diferencia.
    ax.set_xlim(3.8, 5.05)
    ax.set_xlabel("Media (escala 1 a 5; eje recortado en 3,8)")
    ax.set_title(f"Instrumento cualitativo por bloque · {e.get('validas', 0)} respuestas completas")
    ax.legend(loc="lower right")
    fig.savefig(ruta)
    plt.close(fig)
    return True


def g_encuesta_items(d, ruta):
    e = d.get("encuesta") or {}
    items = e.get("items") or []
    if not items:
        return False
    fig, ax = plt.subplots(figsize=(9.2, 5.4))
    y = np.arange(len(items))
    medias = [i["media"] for i in items]
    colores = [AZUL if i < 4 else VERDE if i < 8 else LILA if i < 12 else AMBAR if i < 16 else ROJO
               for i in range(len(items))]
    ax.barh(y, medias, color=colores, height=0.62)
    for yi, i in zip(y, items):
        ax.text(i["media"] + 0.03, yi, f"{i['media']:.2f}", va="center", fontsize=8, color=GRIS)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{i['codigo']}. {i['texto'][:58]}" for i in items], fontsize=7.8)
    ax.invert_yaxis()
    ax.set_xlim(0, 5.3)
    ax.set_xlabel("Media por ítem (escala 1 a 5)")
    ax.set_title("Los 20 ítems del instrumento, agrupados por bloque")
    fig.savefig(ruta)
    plt.close(fig)
    return True


def g_encuesta_escala(d, ruta):
    e = d.get("encuesta") or {}
    escala = e.get("escala") or {}
    if not escala:
        return False
    etiquetas = [str(v) for v in (1, 2, 3, 4, 5)]
    vals = [escala.get(v, 0) for v in etiquetas]
    total = sum(vals) or 1
    fig, ax = plt.subplots(figsize=(7.4, 3.3))
    barras = ax.bar(etiquetas, vals, color=[GRIS, GRIS, AMBAR, AZUL, VERDE], width=0.55)
    for b, v in zip(barras, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + total * 0.012,
                f"{v}\n({100 * v / total:.1f} %)", ha="center", fontsize=8.4, color=GRIS)
    ax.set_xlabel("Puntaje otorgado")
    ax.set_ylabel("Número de respuestas")
    ax.set_title(f"Distribución de las {total:,} respuestas de los 20 ítems".replace(",", "."))
    ax.set_ylim(0, max(vals) * 1.22)
    fig.savefig(ruta)
    plt.close(fig)
    return True


def g_intencion(d, ruta):
    i = (d.get("notebooks") or {}).get("intencion") or {}
    if not i:
        return False
    fig, ejes = plt.subplots(1, 2, figsize=(9.0, 3.3), gridspec_kw={"width_ratios": [1.6, 1]})
    ax = ejes[0]
    etiquetas = ["HR@1", "HR@5", "HR@10"]
    vals = [i.get("hr1", 0), i.get("hr5", 0), i.get("hr10", 0)]
    ax.bar(etiquetas, vals, color=[AZUL, VERDE, LILA], width=0.5)
    for px, v in enumerate(vals):
        ax.text(px, v + 0.12, f"{v:.2f} %", ha="center", fontsize=9, color=GRIS)
    ax.set_ylabel("Acierto (%)")
    ax.set_title(f"Módulo de intención aislado · {i.get('clases', 0):,} clases".replace(",", "."))
    ax.set_ylim(0, max(vals) * 1.3)
    ax = ejes[1]
    ax.bar(["MRR"], [i.get("mrr", 0)], color=AMBAR, width=0.35)
    ax.text(0, i.get("mrr", 0) + 0.0006, f"{i.get('mrr', 0):.4f}", ha="center", fontsize=9, color=GRIS)
    ax.set_ylim(0, max(0.02, i.get("mrr", 0) * 1.4))
    ax.set_title(f"Validación en {i.get('dispositivo_validacion', 'CPU')}")
    fig.tight_layout()
    fig.savefig(ruta)
    plt.close(fig)
    return True


def g_ritmo(d, ruta):
    r = (d.get("turnos") or {}).get("ritmo") or {}
    por_min = r.get("por_minuto") or {}
    if not por_min:
        return False
    etiquetas = list(por_min)
    vals = list(por_min.values())
    x = np.arange(len(vals))
    fig, ax = plt.subplots(figsize=(9.2, 3.1))
    ax.bar(x, vals, color=AZUL, width=0.8)
    ax.axhline(r.get("rpm_prom", 0), color=ROJO, linestyle="--", linewidth=1.2,
               label=f"Promedio {r.get('rpm_prom', 0):.1f} turnos/min")
    ax.set_xlabel("Minuto de la corrida (UTC)")
    ax.set_ylabel("Turnos atendidos")
    ax.set_title("Ritmo de atención de la demo durante la evaluación")
    paso = max(1, len(x) // 12)
    ax.set_xticks(x[::paso])
    ax.set_xticklabels([etiquetas[j][11:] for j in range(0, len(x), paso)], fontsize=7.6, rotation=45)
    ax.legend()
    fig.savefig(ruta)
    plt.close(fig)
    return True


def g_sesiones(d, ruta):
    t = d.get("turnos") or {}
    dist = (t.get("turnos_por_sesion") or {}).get("distribucion") or {}
    if not dist:
        return False
    etiquetas = [str(k) for k in sorted(dist, key=int)]
    vals = [dist[int(k)] for k in etiquetas]
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    ax.bar(etiquetas, vals, color=VERDE, width=0.55)
    for px, v in enumerate(vals):
        ax.text(px, v + max(vals) * 0.02, str(v), ha="center", fontsize=9, color=GRIS)
    ax.set_xlabel("Turnos por sesión")
    ax.set_ylabel("Número de sesiones")
    ax.set_title(f"Estructura conversacional · {t.get('sesiones', 0)} sesiones, "
                 f"{t.get('turnos', 0)} turnos")
    fig.savefig(ruta)
    plt.close(fig)
    return True


FIGURAS = (
    ("g01_convergencia.png", g_convergencia),
    ("g02_ranking.png", g_ranking),
    ("g03_latencia_etapas.png", g_latencia),
    ("g04_latencia_percentiles.png", g_percentiles),
    ("g05_diversidad.png", g_diversidad),
    ("g06_cumplimiento.png", g_cumplimiento),
    ("g07_sensibilidad.png", g_sensibilidad),
    ("g08_encuesta_bloques.png", g_encuesta_bloques),
    ("g09_encuesta_items.png", g_encuesta_items),
    ("g10_encuesta_escala.png", g_encuesta_escala),
    ("g11_intencion.png", g_intencion),
    ("g12_ritmo.png", g_ritmo),
    ("g13_sesiones.png", g_sesiones),
)


def cargar_datos(ruta_ranking: str | None = None, ruta_encuesta: str | None = None) -> dict:
    eventos = leer_turnos()
    ranking = None
    rutas = [ruta_ranking] if ruta_ranking else sorted(glob.glob(str(EVA / "ranking*.json")))
    for r in rutas:
        if r and Path(r).exists():
            ranking = json.loads(Path(r).read_text(encoding="utf-8"))
    encuesta = None
    excel = ruta_encuesta or str(RAIZ / "docs" / "resultados encuesta.xlsx")
    if Path(excel).exists():
        encuesta = analizar_encuesta(excel)
    resumen = None
    r = _ultimo("resumen_*.json")
    if r:
        resumen = json.loads(Path(r).read_text(encoding="utf-8"))
    return {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "turnos": agregar_turnos(eventos),
        "ranking": ranking,
        "encuesta": encuesta,
        "notebooks": leer_notebooks(),
        "resumen_corrida": resumen,
        "detalle_turnos": eventos,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ranking", default=None)
    ap.add_argument("--encuesta", default=None)
    ap.add_argument("--salida", default=str(ASSETS))
    ap.add_argument("--datos", default=str(EVA / "datos_informe.json"))
    args = ap.parse_args()

    d = cargar_datos(args.ranking, args.encuesta)
    carpeta = Path(args.salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    hechas, omitidas = [], []
    for nombre, fn in FIGURAS:
        try:
            (hechas if fn(d, carpeta / nombre) else omitidas).append(nombre)
        except Exception as exc:
            omitidas.append(f"{nombre} ({type(exc).__name__}: {exc})")
    d["figuras"] = hechas
    d["figuras_omitidas"] = omitidas
    ligero = {k: v for k, v in d.items() if k != "detalle_turnos"}
    Path(args.datos).write_text(json.dumps(ligero, ensure_ascii=False, indent=1, default=str),
                                encoding="utf-8")
    print(f"turnos: {d['turnos'].get('turnos', 0)} · sesiones: {d['turnos'].get('sesiones', 0)}")
    print(f"ranking: {'sí' if d['ranking'] else 'no'} · encuesta: "
          f"{d['encuesta'].get('validas', 0) if d['encuesta'] else 0} completas")
    print(f"figuras: {len(hechas)} hechas, {len(omitidas)} omitidas")
    for o in omitidas:
        print("  omitida:", o)
    print("datos:", args.datos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())