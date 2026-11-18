# informe_evaluacion.py — Graficas e informe Word de la evaluación de EchoPulse AI
"""Reúne la telemetría de la VM, la carrera de carga y la encuesta en un .docx.

    python scripts/informe_evaluacion.py graficas
    python scripts/informe_evaluacion.py docx

Los insumos viven fuera del repo (se descargan de la VM con `az vm run-command`),
así que las rutas se pasan por argumentos y tienen un valor por defecto cómodo.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import statistics as st
import unicodedata
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
AZUL, PIZRA, AMBAR, ROJO, VERDE, GRIS = "#3B82F6", "#0F172A", "#F59E0B", "#EF4444", "#10B981", "#94A3B8"
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white", "axes.edgecolor": GRIS,
    "axes.labelcolor": PIZRA, "text.color": PIZRA, "xtick.color": PIZRA, "ytick.color": PIZRA,
    "axes.grid": True, "grid.color": "#E2E8F0", "grid.linewidth": 0.6, "axes.axisbelow": True,
    "font.size": 9, "axes.titlesize": 11, "axes.titleweight": "bold", "legend.frameon": False,
    "font.family": "DejaVu Sans",
})


def percentiles(vals, ps=(50, 90, 99)):
    v = sorted(vals)
    out = {}
    for p in ps:
        k = (len(v) - 1) * p / 100.0
        a, b = int(k), min(int(k) + 1, len(v) - 1)
        out[p] = v[a] + (v[b] - v[a]) * (k - a)
    return out


def leer_json(ruta):
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def leer_carga(ruta):
    registros = []
    for archivo in sorted(glob.glob(str(ruta))):
        for linea in open(archivo, encoding="utf-8"):
            if linea.strip():
                registros.append(json.loads(linea))
    return registros


# ------------------------------------------------------------------ encuesta --

def analizar_encuesta(ruta):
    import openpyxl

    hoja = openpyxl.load_workbook(ruta, data_only=True).worksheets[0]
    filas = list(hoja.iter_rows(min_row=2, values_only=True))
    titulos = [hoja.cell(row=1, column=c).value for c in range(2, 22)]
    validas = [f for f in filas if all(f[i] is not None for i in range(1, 21))]
    otras = len(filas) - len(validas)
    k = 20

    var_items = sum(st.pvariance([f[i] for f in validas]) for i in range(1, k + 1))
    sumas = [sum(f[i] for i in range(1, k + 1)) for f in validas]
    alfa = (k / (k - 1)) * (1 - var_items / st.pvariance(sumas))

    def cov(a, b):
        ma, mb = st.mean(a), st.mean(b)
        n = len(a)
        return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (n - 1)

    columnas = {i: [f[i] for f in validas] for i in range(1, k + 1)}
    vs = {i: cov(columnas[i], columnas[i]) for i in columnas}
    pares = [cov(columnas[i], columnas[j]) / (vs[i] ** 0.5 * vs[j] ** 0.5)
             for i in columnas for j in columnas if i < j]

    items = []
    for i in range(1, k + 1):
        vals = columnas[i]
        items.append({
            "codigo": str(titulos[i - 1]).split(".")[0],
            "texto": str(titulos[i - 1]).split(". ", 1)[1],
            "media": round(st.mean(vals), 2), "sd": round(st.pstdev(vals), 2),
            "p5": round(100 * sum(1 for v in vals if v == 5.0) / len(vals), 1),
            "dist": {str(int(v)): sum(1 for x in vals if x == v) for v in (3.0, 4.0, 5.0)},
        })

    bloques = [("Comprensión de la petición", [1, 2, 3, 4]),
               ("Diversidad y emergentes", [5, 6, 7, 8]),
               ("Explicaciones y lenguaje", [9, 10, 11, 12]),
               ("Usabilidad y rendimiento", [13, 14, 15, 16]),
               ("Satisfacción e intención de uso", [17, 18, 19, 20])]
    bloque_stats = []
    for nombre, idx in bloques:
        vals = [f[i] for f in validas for i in idx]
        sub = [sum(f[i] for i in idx) / len(idx) for f in validas]
        bloque_stats.append({"nombre": nombre, "items": idx, "media": round(st.mean(vals), 3),
                             "sd": round(st.pstdev(sub), 3),
                             "p5": round(100 * sum(1 for v in vals if v == 5.0) / len(vals), 1)})

    comentarios = [str(f[21]).strip() for f in validas if f[21]]
    tiempos = sorted(f[0] for f in validas)
    huecos = [(b - a).total_seconds() for a, b in zip(tiempos, tiempos[1:])]

    return {
        "fuente": str(ruta), "filas": len(filas), "validas": len(validas),
        "sin_responder": otras, "alfa_cronbach": round(alfa, 3),
        "corr_interitem": round(st.mean(pares), 3),
        "media_global": round(st.mean([f[i] for f in validas for i in range(1, k + 1)]), 3),
        "escala": {str(int(v)): sum(1 for f in validas for i in range(1, 21) if f[i] == v) for v in (1, 2, 3, 4, 5)},
        "items": items, "bloques": bloque_stats, "comentarios": comentarios,
        "comentarios_distintos": len(set(comentarios)),
        "comentario_repetido": collections.Counter(comentarios).most_common(1),
        "hora_primera": str(tiempos[0]), "hora_ultima": str(tiempos[-1]),
        "hueco_mediano_s": round(st.median(huecos), 2),
        "huecos_menores_2s": sum(1 for h in huecos if h < 2),
        "marcas": [(t, "plena") for t in tiempos],
        "arranque_validas": str(tiempos[1]),
    }


# -------------------------------------------------------------------- datos --

def cargar_todo(args):
    return {
        "vm": leer_json(args.vm),
        "carga": leer_carga(args.carga),
        "encuesta": analizar_encuesta(args.encuesta),
        "bandas": leer_json(args.bandas) if Path(args.bandas).exists() else None,
        "metrics": leer_json(args.metrics) if Path(args.metrics).exists() else None,
    }


# ------------------------------------------------------------------ gráficas --

def _fig(ancho=8.0, alto=4.0):
    fig, eje = plt.subplots(figsize=(ancho, alto))
    return fig, eje


def _guardar(fig, carpeta, nombre):
    fig.tight_layout()
    fig.savefig(str(Path(carpeta) / nombre), dpi=160)
    plt.close(fig)


def g_latencia(carga, carpeta):
    fig, eje = _fig()
    vals = [r["ms_total"] / 1000 for r in carga if r.get("ms_total")]
    eje.hist(vals, bins=28, color=AZUL, edgecolor="white")
    p = percentiles(vals)
    for valor, etiqueta, color in ((p[50], "p50", VERDE), (p[90], "p90", AMBAR), (p[99], "p99", ROJO)):
        eje.axvline(valor, color=color, linestyle="--", lw=1.4,
                    label=f"{etiqueta} = {valor:.1f} s")
    eje.set_title(f"Latencia de extremo a extremo en la carrera de carga ({len(carga)} turnos)")
    eje.set_xlabel("Segundos desde el envío hasta la respuesta completa")
    eje.set_ylabel("Turnos")
    eje.legend()
    _guardar(fig, carpeta, "g01_latencia_carga.png")


def g_grupos(vm, carpeta):
    fig, eje = _fig()
    orden = ["real", "verif", "carga", "otros"]
    nombres = {"real": "Visitantes reales", "verif": "Verificación", "carga": "Carga sintética",
               "otros": "Diagnóstico"}
    grupos = [g for g in orden if vm["por_grupo"].get(g, {}).get("turnos")]
    ancho = 0.26
    series = [("p50", AZUL), ("p90", AMBAR), ("p99", ROJO)]
    for i, (clave, color) in enumerate(series):
        eje.bar([x + i * ancho for x in range(len(grupos))],
                [vm["por_grupo"][g]["lat_total_ms"][clave] / 1000 for g in grupos],
                ancho, label=clave, color=color)
    eje.set_xticks([x + ancho for x in range(len(grupos))])
    eje.set_xticklabels([f"{nombres[g]}\n{vm['por_grupo'][g]['turnos']} turnos" for g in grupos])
    eje.set_ylabel("Segundos")
    eje.set_title("Percentiles de latencia del servidor según el origen del tráfico")
    eje.legend(ncol=3)
    _guardar(fig, carpeta, "g02_latencia_grupos.png")


def g_etapas(vm, carpeta):
    fig, eje = _fig()
    grupos = ["real", "carga"]
    etapas = ["translation", "retrieval", "reranking", "generation"]
    colores = [GRIS, VERDE, AMBAR, AZUL]
    base = [0.0] * len(grupos)
    for etapa, color in zip(etapas, colores):
        vals = [vm["por_grupo"][g]["etapas_ms"].get(etapa, 0) / 1000 for g in grupos]
        eje.barh(grupos, vals, left=base, label=etapa, color=color)
        for i, v in enumerate(vals):
            if v > 0.35:
                eje.text(base[i] + v / 2, i, f"{v:.2f}", ha="center", va="center", fontsize=8,
                         color="white" if color != AMBAR else PIZRA)
        base = [b + v for b, v in zip(base, vals)]
    eje.set_xlabel("Segundos (media por turno)")
    eje.set_title("Dónde se va el tiempo: la generación con Qwen domina el ciclo")
    eje.legend(ncol=4, bbox_to_anchor=(0, -0.18), loc="upper left")
    _guardar(fig, carpeta, "g03_etapas.png")


def g_rechazos(vm, carpeta):
    fig, eje = _fig()
    grupos = ["real", "carga", "verif", "otros"]
    grupos = [g for g in grupos if vm["por_grupo"].get(g, {}).get("turnos")]
    ok = [vm["por_grupo"][g]["proveedor"].get("custom", 0) for g in grupos]
    mal = [vm["por_grupo"][g]["proveedor"].get("determinista", 0) for g in grupos]
    eje.bar(grupos, ok, color=VERDE, label="Respuesta del LLM aceptada")
    eje.bar(grupos, mal, bottom=ok, color=ROJO, label="Validador rechazó → plantilla")
    for i, (a, b) in enumerate(zip(ok, mal)):
        eje.text(i, a / 2, str(a), ha="center", va="center", color="white", fontsize=9, weight="bold")
        if b:
            eje.text(i, a + b / 2, f"{b}\n{100 * b / (a + b):.0f}%", ha="center", va="center",
                     color="white", fontsize=8, weight="bold")
    eje.set_ylabel("Turnos")
    eje.set_title("Rechazo del validador de respuestas (llm_rechazado == determinista)")
    eje.legend()
    _guardar(fig, carpeta, "g04_rechazos.png")


def g_cobertura(vm, carpeta):
    fig, eje = _fig()
    hist = vm["muestra_global"]["cobertura_m3"]["hist"]
    claves = sorted(hist, key=float)
    vals = [hist[k] for k in claves]
    eje.bar([f"{100 * float(k):.0f}%" for k in claves], vals, color=AZUL)
    for i, v in enumerate(vals):
        eje.text(i, v + 1.5, str(v), ha="center", fontsize=9)
    eje.set_title("Cobertura del transformer de intención por turno (fracción de la tanda\n"
                  "cuyo título existe entre las 38.343 clases entrenadas)")
    eje.set_xlabel("Canciones de la tanda con clase conocida")
    eje.set_ylabel("Turnos")
    _guardar(fig, carpeta, "g05_cobertura_m3.png")


def g_diversidad(vm, carpeta):
    fig, ejes = plt.subplots(1, 2, figsize=(9.6, 4.0))
    grupos = ["real", "carga", "otros"]
    nombres = {"real": "Reales", "carga": "Carga", "otros": "Diagnóstico"}
    eme = [vm["por_grupo"][g]["emergentes"]["prom_turno"] for g in grupos]
    reco = [vm["por_grupo"][g]["reconocidos"]["prom_turno"] for g in grupos]
    ejes[0].bar(nombres.values(), eme, color=VERDE, label="Emergentes")
    ejes[0].bar(nombres.values(), reco, bottom=eme, color=GRIS, label="Reconocidos")
    for i, (a, b) in enumerate(zip(eme, reco)):
        ejes[0].text(i, a / 2, f"{a:.1f}", ha="center", va="center", color="white", fontsize=9)
        ejes[0].text(i, a + b / 2, f"{b:.1f}", ha="center", va="center", color="white", fontsize=9)
    ejes[0].set_ylabel("Canciones por tanda de 10")
    ejes[0].set_title("Composición de la tanda")
    ejes[0].legend(ncol=2)
    pop = [vm["por_grupo"][g]["tarjetas"]["popularity_prom"] for g in grupos]
    ejes[1].bar(nombres.values(), pop, color=AZUL)
    for i, v in enumerate(pop):
        ejes[1].text(i, v + 1, f"{v:.1f}", ha="center", fontsize=9)
    ejes[1].axhline(57.1, color=ROJO, ls="--", lw=1.2, label="media global 57,1")
    ejes[1].set_ylim(0, 75)
    ejes[1].set_ylabel("Popularity del catálogo (0-100)")
    ejes[1].set_title("Fama media de lo recomendado")
    ejes[1].legend()
    _guardar(fig, carpeta, "g06_diversidad.png")


def g_cola(carga, carpeta):
    import datetime

    fig, eje = _fig(9.0, 4.0)
    xs = list(range(1, len(carga) + 1))
    ys = [r["ms_total"] / 1000 for r in carga]
    cs = [ROJO if r["llm"] == "determinista" else AZUL for r in carga]
    eje.scatter(xs, ys, c=cs, s=16, alpha=0.75)
    ventana = 15
    prom = [st.mean(ys[i:i + ventana]) for i in range(0, len(ys) - ventana + 1, ventana)]
    eje.plot(range(ventana, len(ys) + 1, ventana), prom, color=PIZRA, lw=1.6,
             label="media móvil de 15 turnos")
    momentos = [datetime.datetime.fromisoformat(r["timestamp"]) for r in carga]
    rpm = len(carga) / max((momentos[-1] - momentos[0]).total_seconds() / 60, 1e-9)
    eje.set_ylim(0, max(ys) + 2)
    eje.set_xlabel("Turno enviado (orden cronológico)")
    eje.set_ylabel("Segundos")
    eje.set_title(f"La carrera de carga: {rpm:.1f} turnos por minuto contra un único slot de Qwen\n"
                  f"(rojo = respuesta determinista por rechazo del validador)")
    eje.legend()
    _guardar(fig, carpeta, "g07_cola_carga.png")


def g_generos(vm, carpeta):
    fig, eje = _fig()
    datos = vm["muestra_global"]["generos_top"]
    eje.barh([g for g, _ in datos][::-1], [n for _, n in datos][::-1], color=AZUL)
    eje.set_xlabel("Tarjetas recomendadas")
    eje.set_title(f"Reparto de géneros entre las {vm['muestra_global']['tarjetas']['n']:,} "
                  f"tarjetas del log de la VM".replace(",", "."))
    _guardar(fig, carpeta, "g08_generos.png")


def g_items_encuesta(e, carpeta):
    fig, eje = _fig(9.4, 4.6)
    cod = [it["codigo"] for it in e["items"]]
    med = [it["media"] for it in e["items"]]
    sd = [it["sd"] for it in e["items"]]
    eje.bar(cod, med, bottom=3.4, yerr=sd, capsize=2, color=AZUL,
            error_kw={"lw": 0.9, "ecolor": PIZRA})
    eje.axhline(e["media_global"], color=ROJO, ls="--", lw=1.3,
                label=f"media global {e['media_global']:.2f}")
    for i, v in enumerate(med):
        eje.text(i, v + 0.16, f"{v:.2f}", ha="center", fontsize=7)
    eje.set_ylim(3.4, 5.15)
    eje.set_ylabel("Media (escala 1-5)")
    eje.set_xlabel("Ítem de la encuesta")
    eje.set_title(f"Percepción por ítem (n = {e['validas']}) — barras de error = desviación típica")
    eje.legend()
    _guardar(fig, carpeta, "g09_encuesta_items.png")


def g_bloques(e, carpeta):
    fig, eje = _fig()
    nombres = [b["nombre"] for b in e["bloques"]]
    p5 = [b["p5"] for b in e["bloques"]]
    otros = [100 - x for x in p5]
    eje.bar(nombres, p5, color=VERDE, label="Respuestas con 5")
    eje.bar(nombres, otros, bottom=p5, color=AMBAR, label="Respuestas con 3 o 4")
    for i, v in enumerate(p5):
        eje.text(i, v / 2, f"{v:.0f}%", ha="center", va="center", color="white", weight="bold")
    eje.set_ylim(0, 100)
    eje.set_ylabel("Porcentaje de respuestas")
    eje.set_title("Distribución por bloque temático (techo alto: nadie usó 1 ni 2)")
    eje.set_xticks(range(len(nombres)))
    eje.set_xticklabels(nombres, rotation=18, ha="right")
    eje.legend()
    _guardar(fig, carpeta, "g10_encuesta_bloques.png")


def g_crono_encuesta(e, vm, carpeta):
    fig, eje = _fig(9.0, 4.0)
    dias = collections.Counter(m.strftime("%Y-%m-%d") for m, _ in e["marcas"])
    eje.bar(list(dias), list(dias.values()), color=AZUL)
    for i, n in enumerate(dias.values()):
        eje.text(i, n / 2, str(n), ha="center", va="center", color="white", weight="bold")
    eje.set_ylabel("Respuestas completas")
    eje.set_title(f"Respuestas completas por día (n = {e['validas']})")
    _guardar(fig, carpeta, "g11_encuesta_cronos.png")

    # zoom a la ráfaga: los minutos con más tráfico
    fig, eje = _fig(9.0, 4.0)
    minutos = collections.Counter(m.strftime("%Y-%m-%d %H:%M") for m, _ in e["marcas"])
    mas = sorted(minutos.items(), key=lambda kv: -kv[1])[:25]
    eje.bar([k[5:] for k, _ in mas], [v for _, v in mas], color=AMBAR)
    eje.set_ylabel("Respuestas completas")
    eje.set_xlabel("Hora del envío (minuto)")
    eje.set_title(f"Los 25 minutos con más envíos: {e['huecos_menores_2s']} de "
                  f"{e['validas'] - 1} intervalos entre respuestas duraron menos de "
                  f"{2} s (mediana {e['hueco_mediano_s']} s)")
    _guardar(fig, carpeta, "g12_encuesta_rafaga.png")


def g_bandas(bandas, carpeta):
    fig, ejes = plt.subplots(1, 2, figsize=(9.6, 4.0))
    etiquetas = ["Lo que ve\nel visitante\n(puestos 1-3)", "Solo el ranking\ninterno\n(puestos 4-10)"]
    vis, ins = bandas["global"]["visible 1-3"], bandas["global"]["interno 4-10"]
    ejes[0].bar(etiquetas, [vis["emergentes_pct"], ins["emergentes_pct"]], color=VERDE, label="Emergentes")
    ejes[0].bar(etiquetas, [vis["reconocidos_pct"], ins["reconocidos_pct"]],
                bottom=[vis["emergentes_pct"], ins["emergentes_pct"]], color=GRIS, label="Reconocidos")
    for i, (a, b) in enumerate([(vis["emergentes_pct"], vis["reconocidos_pct"]),
                                (ins["emergentes_pct"], ins["reconocidos_pct"])]):
        ejes[0].text(i, a / 2, f"{a:.0f}%", ha="center", va="center", color="white", weight="bold")
        ejes[0].text(i, a + b / 2, f"{b:.0f}%", ha="center", va="center", color="white", weight="bold")
    ejes[0].set_ylim(0, 118)
    ejes[0].set_yticks([0, 20, 40, 60, 80, 100])
    ejes[0].set_ylabel("Porcentaje de la tanda")
    ejes[0].set_title("El descubrimiento de emergentes se queda fuera de la pantalla")
    ejes[0].legend(ncol=2)

    grupos = [("real", "Visitantes reales"), ("carga", "Carga sintética")]
    x = range(len(grupos))
    ancho = 0.35
    ejes[1].bar([i - ancho / 2 for i in x], [bandas[g]["visible 1-3"]["popularity"] for g, _ in grupos],
                ancho, color=AZUL, label="Popularity media 1-3")
    ejes[1].bar([i + ancho / 2 for i in x], [bandas[g]["interno 4-10"]["popularity"] for g, _ in grupos],
                ancho, color=AMBAR, label="Popularity media 4-10")
    for i, (g, _) in enumerate(grupos):
        ejes[1].text(i - ancho / 2, bandas[g]["visible 1-3"]["popularity"] + 1,
                     f"{bandas[g]['visible 1-3']['popularity']:.0f}", ha="center", fontsize=8)
        ejes[1].text(i + ancho / 2, bandas[g]["interno 4-10"]["popularity"] + 1,
                     f"{bandas[g]['interno 4-10']['popularity']:.0f}", ha="center", fontsize=8)
    ejes[1].set_xticks(list(x))
    ejes[1].set_xticklabels([n for _, n in grupos])
    ejes[1].set_ylim(0, 75)
    ejes[1].set_ylabel("Popularity del catálogo (0-100)")
    ejes[1].set_title("Los tres primeros puestos son los más famosos")
    ejes[1].legend()
    _guardar(fig, carpeta, "g13_bandas.png")


def hacer_graficas(args, carpeta, d):
    vm, carga, encuesta, bandas = d["vm"], d["carga"], d["encuesta"], d["bandas"]
    Path(carpeta).mkdir(parents=True, exist_ok=True)
    g_latencia(carga, carpeta)
    g_grupos(vm, carpeta)
    g_etapas(vm, carpeta)
    g_rechazos(vm, carpeta)
    g_cobertura(vm, carpeta)
    g_diversidad(vm, carpeta)
    g_cola(carga, carpeta)
    g_generos(vm, carpeta)
    if bandas:
        g_bandas(bandas, carpeta)
    g_items_encuesta(encuesta, carpeta)
    g_bloques(encuesta, carpeta)
    g_crono_encuesta(encuesta, vm, carpeta)
    return sorted(p.name for p in Path(carpeta).glob("*.png"))


def main():
    parser = argparse.ArgumentParser()
    temp = os.environ.get("TEMP", ".")
    parser.add_argument("--vm", default=os.path.join(temp, "eva", "vm_agg.json"))
    parser.add_argument("--bandas", default=os.path.join(temp, "eva", "bandas.json"))
    parser.add_argument("--metrics", default=os.path.join(temp, "eva", "metrics_live.json"))
    parser.add_argument("--encuesta", default=str(RAIZ.parent / "docs" / "resultados encuesta.xlsx"))
    parser.add_argument("--carga", default=str(RAIZ / "logs_carga" / "carga_*.jsonl"))
    parser.add_argument("--carpeta", default=str(RAIZ.parent / "docs" / "informe_evaluacion_assets"))
    parser.add_argument("--docx", default=str(RAIZ.parent / "docs" / "EchoPulse_AI_informe_evaluacion.docx"))
    parser.add_argument("accion", nargs="?", default="graficas", choices=["graficas", "docx", "todo"])
    args = parser.parse_args()

    datos = cargar_todo(args)
    if args.accion in ("graficas", "todo"):
        print("\n".join(hacer_graficas(args, args.carpeta, datos)))
    if args.accion in ("docx", "todo"):
        from informe_docx import escribir  # noqa: E402
        escribir(args, datos)


if __name__ == "__main__":
    main()
