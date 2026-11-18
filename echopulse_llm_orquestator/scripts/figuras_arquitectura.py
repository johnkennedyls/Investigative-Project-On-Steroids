# scripts/figuras_arquitectura.py - Diagramas de arquitectura para la monografía
"""Dibuja los esquemas del sistema tal como quedó implementado.

Cada diagrama se construye con las cotas y constantes que viven en el código
(app.py, rerank.py, conversacion.py, deploy/azure-compose.yaml) y con las cifras
medidas que consolida graficas_final.py en build/eva/datos_informe.json. No se
dibuja ningún componente que no exista en el repositorio.

    python scripts/figuras_arquitectura.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

RAIZ = Path(__file__).resolve().parents[2]
EVA = RAIZ / "build" / "eva"
SALIDA = RAIZ / "docs" / "monografia_assets"

AZUL = "#1D4ED8"
VERDE = "#0F766E"
AMBAR = "#B45309"
LILA = "#6D28D9"
GRIS = "#475569"
ROJO = "#B42318"
TEXTO = "#1F2937"
LINEA = "#64748B"

FONDOS = {AZUL: "#EFF6FF", VERDE: "#ECFDF5", AMBAR: "#FFFBEB",
          LILA: "#F5F3FF", GRIS: "#F8FAFC", ROJO: "#FEF2F2"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "figure.dpi": 200, "savefig.dpi": 200, "savefig.bbox": "tight",
})


def mil(valor) -> str:
    try:
        return f"{int(round(float(valor))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def nm(valor, dec=1) -> str:
    if valor is None:
        return "—"
    return f"{valor:,.{dec}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def lienzo(alto, ancho=10.8):
    fig, ax = plt.subplots(figsize=(ancho, alto * ancho / 100))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, alto)
    ax.axis("off")
    fig.subplots_adjust(left=0.005, right=0.995, top=0.995, bottom=0.005)
    return fig, ax


def banda(ax, x, y, w, h, titulo, color=GRIS):
    ax.add_patch(Rectangle((x, y), w, h, facecolor="#FCFCFD", edgecolor="#CBD5E1",
                           lw=0.9, linestyle=(0, (4, 3)), zorder=0))
    if titulo:
        ax.text(x + 1.4, y + h - 1.1, titulo, va="top", ha="left", fontsize=9.2,
                fontweight="bold", color=color, zorder=3)


def caja(ax, x, y, w, h, titulo, cuerpo="", color=AZUL, fs=8.3, ts=9.0):
    ax.add_patch(Rectangle((x, y), w, h, facecolor=FONDOS[color], edgecolor=color,
                           lw=1.15, zorder=2))
    cx = x + w / 2
    if cuerpo:
        ax.text(cx, y + h - 1.15, titulo, va="top", ha="center", fontsize=ts,
                fontweight="bold", color=color, zorder=3, linespacing=1.3)
        ax.text(cx, y + (h - 3.1) / 2, cuerpo, va="center", ha="center", fontsize=fs,
                color=TEXTO, zorder=3, linespacing=1.45)
    else:
        ax.text(cx, y + h / 2, titulo, va="center", ha="center", fontsize=ts,
                fontweight="bold", color=color, zorder=3, linespacing=1.4)


def flecha(ax, p1, p2, etiqueta=None, color=LINEA, punteada=False, rad=0.0, fs=7.6):
    ax.annotate("", xy=p2, xytext=p1, zorder=1,
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.25,
                                shrinkA=1.5, shrinkB=1.5,
                                linestyle="--" if punteada else "-",
                                connectionstyle=f"arc3,rad={rad}"))
    if etiqueta:
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        ax.text(mx, my, etiqueta, ha="center", va="center", fontsize=fs, color=color,
                zorder=4, bbox=dict(boxstyle="round,pad=0.18", facecolor="white",
                                    edgecolor="none", alpha=0.92))


def ruta(ax, puntos, color=LINEA, punteada=True, etiqueta=None, fs=7.6):
    """Polilínea con punta de flecha en el último tramo."""
    xs = [p[0] for p in puntos[:-1]]
    ys = [p[1] for p in puntos[:-1]]
    ax.plot(xs, ys, color=color, lw=1.25, zorder=1,
            linestyle="--" if punteada else "-")
    flecha(ax, puntos[-2], puntos[-1], etiqueta=etiqueta, color=color,
           punteada=punteada, fs=fs)


def guardar(fig, nombre):
    SALIDA.mkdir(parents=True, exist_ok=True)
    destino = SALIDA / nombre
    fig.savefig(destino, facecolor="white")
    plt.close(fig)
    print(f"  {nombre}")
    return destino


# ------------------------------------------------------- 1. datos y modelos --

def f_datos(d):
    ins = (d.get("ranking") or {}).get("insumos") or {}
    nb = d.get("notebooks") or {}
    it = nb.get("intencion") or {}
    perdida = nb.get("perdida") or []
    fig, ax = lienzo(64)
    banda(ax, 1, 1.5, 98, 61, "PROCESAMIENTO OFFLINE · consolidación de datos y entrenamiento")

    fuentes = [
        (3.0, "Million Song Dataset", "descriptores de audio\ny metadatos [5]", AZUL),
        (26.5, "WASABI Songs", "análisis cultural,\nde letra y de audio [6]", AZUL),
        (50.0, "Lyrics 1950-2019", "letras limpias\nventana 1950–2019 [7]", AZUL),
        (73.5, "TalkPlayData 2", "diálogos sintéticos\noyente–música [8]", LILA),
    ]
    for x, tit, cue, col in fuentes:
        caja(ax, x, 45, 23, 9, tit, cue, color=col)

    caja(ax, 3, 32, 68, 8.5, "ETL · limpieza, normalización y unión por identificadores",
         "unión MSD ∩ WASABI ∩ letras · cuantiles de ánimo por columna · sin identificadores expuestos",
         color=VERDE)
    caja(ax, 73.5, 32, 23, 8.5, "Corpus de intención", "se entrena aparte:\nno entra al catálogo",
         color=LILA)

    caja(ax, 3, 18.5, 21.5, 9.5, "Tabla maestra",
         f"{mil(ins.get('pistas'))} pistas × 48 columnas\nparticiones train / val / test", color=VERDE)
    caja(ax, 26.5, 18.5, 21.5, 9.5, "Rasgos y vocabulario",
         f"6 rasgos de ánimo · 26 técnicos\nvocabulario {mil(nb.get('vocabulario'))} (frec. ≥ 2)",
         color=VERDE)
    caja(ax, 50, 18.5, 21.5, 9.5, "Índice de fama",
         f"{mil(545983)} entradas · consulta en línea\nartista y título → popularidad", color=AMBAR)

    caja(ax, 3, 4.5, 52, 10, "M2 · Transformer de contenido",
         "d_model 512 · 8 cabezas · 6 capas · atención cruzada\n"
         f"{nb.get('epocas', len(perdida))} épocas · lote 32 · GPU · "
         f"MSE {nm(perdida[0], 4) if perdida else '—'} → {nm(perdida[-1], 4) if perdida else '—'}",
         color=AZUL)
    caja(ax, 60, 4.5, 36, 10, "M3 · Transformer de intención",
         f"d_model 256 · 8 cabezas · 4 capas\n{mil(it.get('clases'))} clases · AdamW 1e-4 · paciencia 5",
         color=LILA)

    for x, _, _, _ in fuentes[:3]:
        flecha(ax, (x + 11.5, 45), (x + 11.5, 40.5))
    flecha(ax, (85, 45), (85, 40.5))
    for x in (13.75, 37.25, 60.75):
        flecha(ax, (x, 32), (x, 28))
    flecha(ax, (13.75, 18.5), (13.75, 14.5))
    flecha(ax, (37.25, 18.5), (37.25, 14.5))
    flecha(ax, (85, 32), (85, 14.5))
    ax.text(50, 2.2, "Los artefactos entrenados (checkpoints y embeddings) se publican en un repositorio "
            "de artefactos y se descargan al arrancar la demo.",
            ha="center", va="center", fontsize=7.8, color=GRIS, style="italic")
    return guardar(fig, "arq01_datos.png")


# --------------------------------------------------------- 2. pipeline turno --

def f_turno(d):
    t = d.get("turnos") or {}
    fig, ax = lienzo(72)
    banda(ax, 1, 27, 98, 43, "PROCESAMIENTO EN LÍNEA · un turno de conversación")

    arriba = [
        (1, "1 · Petición", "texto o voz en español\ninterfaz web pública", AZUL),
        (21, "2 · Traducción e intención", "ES → EN + 2 a 5 keywords\nLLM o heurística determinista", AZUL),
        (41, "3 · Perfil del turno", "género, ánimo, época\nherencia del turno anterior", AZUL),
        (61, "4 · M2 retrieval", "coseno + Jaccard léxico\nk = 30 candidatas", VERDE),
        (81, "5 · M3 intención", "probabilidad por canción\nsobre las candidatas", LILA),
    ]
    for x, tit, cue, col in arriba:
        caja(ax, x, 53, 18, 11, tit, cue, color=col, ts=8.6, fs=7.9)
    for i in range(4):
        flecha(ax, (arriba[i][0] + 18, 58.5), (arriba[i + 1][0], 58.5))

    abajo = [
        (81, "6 · Fusión", "0,70 similitud + 0,30 intención\nmediana neutra sin clase M3", LILA),
        (61, "7 · Reglas de tanda", "×(1 − 0,60·desvío ánimo)\n×(1 − 0,50·desvío género)\nmáx. 2 por artista", AMBAR),
        (41, "8 · Voz del agente", "Qwen2.5-1.5B en CPU\ntemperatura 0,5 · ctx 4096", AZUL),
        (21, "9 · Validador", "cadena de 8 controles\nrespaldo determinista", ROJO),
        (1, "10 · Respuesta", "3 destacadas de 10 tarjetas\nnombres reales + enlaces", VERDE),
    ]
    for x, tit, cue, col in abajo:
        caja(ax, x, 33, 18, 12, tit, cue, color=col, ts=8.6, fs=7.9)
    flecha(ax, (90, 53), (90, 45))
    for i in range(4):
        flecha(ax, (abajo[i][0], 39), (abajo[i + 1][0] + 18, 39))

    banda(ax, 1, 3, 98, 21, "SERVICIOS TRANSVERSALES · aplican a todos los turnos", color=GRIS)
    caja(ax, 3, 6.5, 30, 12, "Registro del turno",
         "evento JSONL: ranking de 10, perfil,\ncobertura M3, latencias por etapa,\nproveedor de la voz",
         color=GRIS, fs=7.9)
    caja(ax, 35, 6.5, 30, 12, "Memoria de sesión",
         "perfil heredado entre turnos ·\npistas ya recomendadas excluidas ·\ncontador de turno",
         color=GRIS, fs=7.9)
    caja(ax, 67, 6.5, 30, 12, "Limitador por dirección",
         "12 turnos por minuto y por IP ·\nventana deslizante · protege los\n2 núcleos de la máquina",
         color=GRIS, fs=7.9)
    flecha(ax, (10, 33), (10, 24), etiqueta="evento", fs=7.4)
    ax.text(50, 1.2, f"Corpus medido: {mil(t.get('turnos'))} turnos en {mil(t.get('sesiones'))} sesiones "
            "contra la demo desplegada.", ha="center", va="center", fontsize=7.8,
            color=GRIS, style="italic")
    return guardar(fig, "arq02_turno.png")


# ------------------------------------------------------------- 3. M2 detalle --

def f_m2(d):
    nb = d.get("notebooks") or {}
    fig, ax = lienzo(62)
    ax.text(50, 60, "M2 · TRANSFORMER DE CONTENIDO (TABULAR + LÍRICO)", ha="center",
            va="center", fontsize=10.5, fontweight="bold", color=AZUL)

    caja(ax, 2, 46, 44, 9, "Letra de la canción",
         f"tokens · vocabulario {mil(nb.get('vocabulario'))} · max_len 151", color=AZUL)
    caja(ax, 54, 46, 44, 9, "Rasgos técnicos y de ánimo",
         "26 componentes técnicos + 6 cuantiles de ánimo", color=VERDE)
    caja(ax, 2, 33, 44, 9, "Embedding de letra + posición",
         "d_model = 512 · codificación posicional aprendida", color=AZUL)
    caja(ax, 54, 33, 44, 9, "Proyección lineal a 512",
         "26 → 512 · normalización de cuantiles", color=VERDE)
    caja(ax, 2, 18, 96, 12, "Decodificador Transformer con atención cruzada",
         "6 capas · 8 cabezas · la letra actúa como consulta y lo técnico como clave\n"
         "la fusión multimodal ocurre dentro de la atención, no como concatenación previa",
         color=LILA, ts=9.6)
    caja(ax, 2, 4, 44, 10, "E_song · embedding de contenido",
         "512 dimensiones por pista\n5.710 vectores en el índice local", color=AZUL)
    caja(ax, 54, 4, 44, 10, "Uso en línea",
         "similitud coseno consulta–pista\nmezcla con Jaccard léxico → k = 30", color=VERDE)

    for x in (24, 76):
        flecha(ax, (x, 46), (x, 42))
        flecha(ax, (x, 33), (x, 30))
        flecha(ax, (x, 18), (x, 14))
    return guardar(fig, "arq03_m2.png")


# ------------------------------------------------------------- 4. M3 detalle --

def f_m3(d):
    it = (d.get("notebooks") or {}).get("intencion") or {}
    fig, ax = lienzo(56)
    ax.text(50, 54, "M3 · TRANSFORMER DE INTENCIÓN CONVERSACIONAL", ha="center",
            va="center", fontsize=10.5, fontweight="bold", color=LILA)

    pasos = [
        (1, "Consulta", "diálogo del oyente\ntraducido a inglés"),
        (21, "Tokens", "max_len 512\nvocabulario propio"),
        (41, "Embedding", "d_model 256\n+ posición"),
        (61, "Transformer", "4 capas · 8 cabezas\nfeed-forward 1024"),
        (81, "Softmax", f"{mil(it.get('clases'))} clases\nde canción"),
    ]
    for x, tit, cue in pasos:
        caja(ax, x, 38, 18, 11, tit, cue, color=LILA, ts=8.8, fs=8.0)
    for i in range(4):
        flecha(ax, (pasos[i][0] + 18, 43.5), (pasos[i + 1][0], 43.5))

    banda(ax, 1, 4, 98, 26, "EVIDENCIA DEL MÓDULO Y PAPEL EN EL AGENTE", color=GRIS)
    caja(ax, 3, 8, 30, 15, "Entrenamiento",
         "TalkPlayData 2 · AdamW [18]\ntasa 1e-4 · lote 32\npaciencia 5 · parada temprana",
         color=LILA, fs=8.0)
    caja(ax, 35, 8, 30, 15, "Validación aislada",
         f"{mil(it.get('muestras'))} muestras en CPU\nMRR {nm(it.get('mrr'), 4)} · HR@1 {nm(it.get('hr1'), 2)} %\n"
         f"HR@5 {nm(it.get('hr5'), 2)} % · HR@10 {nm(it.get('hr10'), 2)} %",
         color=AMBAR, fs=8.0)
    caja(ax, 67, 8, 30, 15, "Uso en el agente",
         "reordena las 30 candidatas de M2\naporta el 30 % de la mezcla final\ncobertura registrada por turno",
         color=VERDE, fs=8.0)
    flecha(ax, (90, 38), (84, 23), etiqueta="probabilidades", fs=7.4)
    return guardar(fig, "arq04_m3.png")


# ------------------------------------------------------------ 5. despliegue --

def f_despliegue(d):
    fig, ax = lienzo(62)
    banda(ax, 30, 4, 68, 56, "MÁQUINA VIRTUAL AZURE · Standard_B2as_v2 · 2 vCPU · 7,9 GiB", color=GRIS)

    caja(ax, 2, 40, 24, 12, "Oyente", "navegador o voz\nHTTPS público\nsin instalar nada", color=AZUL)
    caja(ax, 2, 24, 24, 10, "Repositorio de artefactos",
         "checkpoints M2 y M3\nembeddings y tabla maestra", color=VERDE)
    caja(ax, 2, 8, 24, 10, "Equipo del autor",
         "administración por SSH\nclave .pem solo en el PC", color=GRIS)

    caja(ax, 33, 40, 30, 12, "app", "Flask + Gunicorn :7860\nM2 · M3 · validador\n12 turnos/min por IP",
         color=AZUL, ts=9.4)
    caja(ax, 66, 40, 29, 12, "qwen", "llama.cpp server :8080\nQwen2.5-1.5B GGUF Q4_K_M\nctx 4096 · 2 hilos · parallel 1",
         color=LILA, ts=9.4, fs=7.9)
    caja(ax, 33, 26, 62, 10, "túneles HTTPS (contenedores)",
         "tunnel-cf · cloudflared, URL pública sin dominio propio\n"
         "tunnel · ngrok, enlace fijo de respaldo · el TLS termina fuera de la VM",
         color=VERDE, fs=8.0)
    caja(ax, 33, 8, 62, 12, "Volúmenes persistentes",
         "qwen-modelos (GGUF) · app-logs (eventos JSONL de cada turno)\n"
         "la tabla maestra y los checkpoints viajan en la imagen · reinicio sin pérdida de registro",
         color=AMBAR, fs=8.0)

    flecha(ax, (26, 43), (33, 31), etiqueta="HTTPS", fs=7.6)
    flecha(ax, (48, 36), (48, 40))
    flecha(ax, (63, 46), (66, 46), etiqueta="API OpenAI", fs=7.2)
    ruta(ax, [(26, 29), (28.5, 29), (28.5, 56), (48, 56), (48, 52)],
         etiqueta="descarga al arrancar", fs=7.2)
    flecha(ax, (26, 13), (30, 13), etiqueta="SSH", punteada=True, fs=7.4)
    ax.text(50, 1.8, "El grupo de seguridad cierra los puertos entrantes: la VM solo hace conexiones "
            "salientes hacia el túnel. Los tokens viven en archivos de entorno restringidos, fuera del repositorio.",
            ha="center", va="center", fontsize=7.6, color=GRIS, style="italic")
    return guardar(fig, "arq05_despliegue.png")


# ------------------------------------------------------- 6. protocolo eval --

def f_evaluacion(d):
    t = d.get("turnos") or {}
    r = d.get("ranking") or {}
    ins = r.get("insumos") or {}
    fig, ax = lienzo(60)
    ax.text(50, 58, "PROTOCOLO DE EVALUACIÓN · relevancia derivada del catálogo", ha="center",
            va="center", fontsize=10.5, fontweight="bold", color=VERDE)

    caja(ax, 1, 42, 30, 11, "Corpus de turnos",
         f"{mil(t.get('turnos'))} turnos · {mil(t.get('sesiones'))} sesiones\nJSONL con el ranking de 10",
         color=AZUL)
    caja(ax, 35, 42, 30, 11, "Catálogo local",
         f"{mil(ins.get('pistas'))} pistas × 48 columnas\nidéntico al que sirve la demo", color=VERDE)
    caja(ax, 69, 42, 30, 11, "Perfil prometido",
         "género pedido + ánimo objetivo\nheredado entre turnos", color=AMBAR)

    caja(ax, 1, 25, 98, 12, "Conjunto relevante R por turno",
         "pista del género pedido cuyo desvío de ánimo, en cuantiles, no supera el umbral u = 0,25\n"
         "ganancia gradada = 1 − desvío · IDCG con las diez mejores del catálogo · Recall@10 sobre min(|R|, 10)",
         color=LILA, ts=9.6)

    caja(ax, 1, 8, 47, 12, "Métricas de orden",
         "HR@1 · HR@3 · Recall@10\nMRR · NDCG@10 · error estándar", color=AZUL)
    caja(ax, 52, 8, 47, 12, "Comparación y robustez",
         "3 líneas base: popularidad, Jaccard léxico, aleatorio\n"
         "3 variantes de relevancia · umbrales 0,15 y 0,35", color=VERDE)

    for x in (16, 50, 84):
        flecha(ax, (x, 42), (x, 37))
    flecha(ax, (24, 25), (24, 20))
    flecha(ax, (76, 25), (76, 20))
    ax.text(50, 3.4, f"{mil(r.get('turnos_juzgados'))} turnos juzgables · "
            f"{mil(t.get('turnos_no_juzgables'))} sin perfil de género · las tandas de 3 tarjetas se "
            "rellenan a 10 para comparar en igualdad de condiciones.",
            ha="center", va="center", fontsize=7.8, color=GRIS, style="italic")
    return guardar(fig, "arq06_evaluacion.png")


def main() -> int:
    ruta = EVA / "datos_informe.json"
    d = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    if not d:
        print("aviso: sin datos_informe.json; los diagramas salen sin cifras medidas")
    print("figuras de arquitectura:")
    for fn in (f_datos, f_turno, f_m2, f_m3, f_despliegue, f_evaluacion):
        fn(d)
    print(f"salida: {SALIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())