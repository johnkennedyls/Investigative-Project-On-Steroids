# scripts/monografia.py - Monografía de grado en Word (guías FUP de monografía)
"""Redacta la monografía que resume toda la investigación de EchoPulse AI.

La estructura sigue las dos guías entregadas (docs/guia monografia 1.docx y
docs/guia monografia 2.docx): portada doble, página de aprobación, dedicatoria,
agradecimientos, resumen y abstract con palabras clave, índices, introducción y
seis capítulos (aspectos generales, marco de referencia, arquitectura y
métodos, datos y despliegue, evaluación, conclusiones y trabajo futuro), más
referencias IEEE y anexos.

El texto está en tercera persona y en español, con prosa original. Todas las
cifras salen de build/eva/datos_informe.json y build/eva/ranking.json, que a su
vez proceden de los turnos registrados contra la demo desplegada, del catálogo
local y de las salidas de los notebooks de entrenamiento. Las figuras de
arquitectura las produce scripts/figuras_arquitectura.py.

    python scripts/graficas_final.py          # cifras + figuras de resultados
    python scripts/figuras_arquitectura.py    # diagramas de arquitectura
    python scripts/monografia.py              # este documento
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bibliografia as bib  # noqa: E402
from informe_docx import (  # noqa: E402
    GRIS, PIZRA, ROJO, _campo_page, caja, figura, h1, h2, mixto, nm, par,
    preparar, tabla, viñetas,
)

RAIZ = Path(__file__).resolve().parents[2]
EVA = RAIZ / "build" / "eva"
ARQ = RAIZ / "docs" / "monografia_assets"
RES = RAIZ / "docs" / "informe_final_assets"

TITULO = "AGENTE RECOMENDADOR DE MÚSICA MULTIMODAL BASADO EN TRANSFORMERS"
SUBTITULO = "Monografía del proyecto EchoPulse AI: consolidación de datos, " \
            "arquitectura local, despliegue continuo y evaluación por turnos"
AUTOR = "JOHN KENNEDY LANDAZURI SANDOVAL"
DIRECTOR = "CRISTIAN CAMILO ORDOÑEZ QUINTERO"
CODIRECTOR = "CRISTIAN MENDEZ RODRÍGUEZ"
GRUPO = "GRUPO DE INVESTIGACIÓN IMS/LOGICIEL"
CIUDAD = "Popayán, noviembre de 2026"

PREGUNTA = ("¿Puede un recomendador musical multimodal local mejorar la diversidad y el "
            "descubrimiento de artistas emergentes sin sacrificar precisión?")
OBJ_GENERAL = ("Diseñar y evaluar un sistema de recomendación musical multimodal local que "
               "priorice la afinidad de contenido para mejorar la diversidad y el "
               "descubrimiento de artistas emergentes.")
OBJ_ESPECIFICOS = (
    "Consolidar datos musicales en una arquitectura local.",
    "Entrenar un modelo Transformer con fusión multimodal.",
    "Comparar precisión, diversidad, intención y latencia frente a líneas base.",
)

# Registro ordenado de figuras y tablas: el número del caption y el de los
# índices salen del mismo lugar, así no se desincronizan.
FIGS = [
    ("arq02_turno.png", "Pipeline de un turno de conversación en el agente desplegado."),
    ("arq03_m2.png", "Transformer de contenido del Módulo 2: fusión de letra y rasgos mediante atención cruzada."),
    ("arq04_m3.png", "Transformer de intención del Módulo 3: evidencia de entrenamiento, validación y uso."),
    ("arq01_datos.png", "Consolidación offline: fuentes, ETL, tabla maestra, índice de fama y entrenamiento."),
    ("g01_convergencia.png", "Convergencia del Transformer de contenido (pérdida MSE por época, escala logarítmica)."),
    ("g11_intencion.png", "Validación aislada del módulo de intención sobre el catálogo completo de clases."),
    ("arq05_despliegue.png", "Despliegue continuo: contenedores, túneles HTTPS y volúmenes persistentes."),
    ("arq06_evaluacion.png", "Protocolo de evaluación con relevancia derivada del catálogo."),
    ("g13_sesiones.png", "Distribución de turnos por sesión en el corpus de evaluación."),
    ("g12_ritmo.png", "Ritmo de turnos por minuto durante la corrida contra la demo desplegada."),
    ("g02_ranking.png", "Métricas de orden del sistema frente a las tres líneas base (relevancia gradada)."),
    ("g07_sensibilidad.png", "Sensibilidad de las métricas al umbral de desvío de ánimo."),
    ("g05_diversidad.png", "Diversidad de la tanda: artistas y géneros distintos y mezcla emergente-reconocido."),
    ("g06_cumplimiento.png", "Cumplimiento del género pedido y distribución del desvío de ánimo."),
    ("g03_latencia_etapas.png", "Latencia media por etapa del turno."),
    ("g04_latencia_percentiles.png", "Percentiles de latencia declarada por el servidor y medida en el cliente."),
    ("g08_encuesta_bloques.png", "Medias por bloque temático del instrumento cualitativo (eje truncado y declarado)."),
    ("g09_encuesta_items.png", "Media y desviación típica de los veinte ítems del instrumento."),
    ("g10_encuesta_escala.png", "Distribución de las respuestas en la escala de cinco puntos."),
]
TABS = [
    "Fases de la metodología y articulación con los objetivos específicos.",
    "Observaciones del evaluador del anteproyecto y su atención en este trabajo.",
    "Fuentes de datos y papel de cada una en el sistema.",
    "Hiperparámetros y resultado del entrenamiento del Módulo 2.",
    "Validación aislada del Módulo 3 frente a la referencia de azar.",
    "Servicios del despliegue y decisión de diseño que cada uno deja ver.",
    "Correcciones de la etapa final y su verificación.",
    "Composición del corpus de evaluación por turnos y sesiones.",
    "Métricas de orden con relevancia gradada (u = 0,25) y error estándar.",
    "Variantes de relevancia: ideal de diez y conjunto amplio binario.",
    "Sensibilidad de las métricas al umbral de desvío de ánimo.",
    "Diversidad y descubrimiento en la tanda recomendada.",
    "Coherencia entre el perfil prometido y la tanda entregada.",
    "Latencia por etapa y percentiles del turno completo.",
    "Voz conversacional e intención registradas por turno.",
    "Descriptivos por bloque temático del instrumento cualitativo.",
    "Resumen del instrumento y consistencia interna observada.",
    "Resultados esperados por objetivo y resultado alcanzado medido.",
]


def mil(v) -> str:
    try:
        return f"{int(round(float(v))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def pc(v, dec=1) -> str:
    return "—" if v is None else nm(v, dec)


def seg(v) -> str:
    return "—" if v is None else nm(float(v) / 1000.0, 1)


def h3(doc, texto):
    return doc.add_heading(texto, level=3)


def fig(doc, n):
    archivo, titulo = FIGS[n - 1]
    carpeta = ARQ if archivo.startswith("arq") else RES
    figura(doc, carpeta, archivo, f"Figura {n}. {titulo}",
           ancho=16.2 if archivo.startswith("arq") else 15.6)


def tab(doc, n, cabeceras, filas, anchos=None, size=8.5, der=()):
    tabla(doc, cabeceras, filas, anchos=anchos, size=size, alineado_der=der,
          caption=f"Tabla {n}. {TABS[n - 1]}")


def salto(doc):
    doc.add_page_break()


def campo_toc(doc):
    p = doc.add_paragraph()
    r = p.add_run()
    inicio = OxmlElement("w:fldChar")
    inicio.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = ' TOC \\o "1-3" \\h \\z \\u '
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    texto = OxmlElement("w:t")
    texto.text = ("El paginado de este índice se completa al abrir el documento en Word "
                  "y aceptar la actualización de campos.")
    fin = OxmlElement("w:fldChar")
    fin.set(qn("w:fldCharType"), "end")
    for nodo in (inicio, instr, sep, texto, fin):
        r._r.append(nodo)


def actualizar_campos(doc):
    ajustes = doc.settings.element
    nodo = OxmlElement("w:updateFields")
    nodo.set(qn("w:val"), "true")
    ajustes.append(nodo)


# ------------------------------------------------------------- preliminar --

def portadas(doc):
    for _ in range(2):
        doc.add_paragraph()
    par(doc, TITULO, size=17, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=10)
    par(doc, SUBTITULO, size=11.5, color=GRIS, italic=True,
        align=WD_ALIGN_PARAGRAPH.CENTER, after=24)
    par(doc, AUTOR, size=13, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=24)
    par(doc, "Trabajo de grado para optar al título de:", size=11,
        align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    par(doc, "Ingeniero de Sistemas", size=12, bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER, after=24)
    par(doc, f"Director: {DIRECTOR}", size=11, align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    par(doc, f"Codirector: {CODIRECTOR}", size=11, align=WD_ALIGN_PARAGRAPH.CENTER, after=28)
    for linea in ("FUNDACIÓN UNIVERSITARIA DE POPAYÁN", "FACULTAD DE INGENIERÍA",
                  "PROGRAMA DE INGENIERÍA DE SISTEMAS", GRUPO, CIUDAD):
        par(doc, linea, size=10.5, bold=linea.startswith("FUNDACIÓN"),
            align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    salto(doc)

    for _ in range(2):
        doc.add_paragraph()
    par(doc, TITULO, size=15, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=16)
    par(doc, AUTOR, size=12, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=20)
    par(doc, "Trabajo de grado presentado a la Facultad de Ingeniería de la Fundación "
             "Universitaria de Popayán para obtener el título de Ingeniero de Sistemas",
        size=11, align=WD_ALIGN_PARAGRAPH.CENTER, after=20)
    par(doc, f"Director: {DIRECTOR}", size=11, align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    par(doc, f"Codirector: {CODIRECTOR}", size=11, align=WD_ALIGN_PARAGRAPH.CENTER, after=28)
    for linea in ("FUNDACIÓN UNIVERSITARIA DE POPAYÁN", "FACULTAD DE INGENIERÍA",
                  "PROGRAMA DE INGENIERÍA DE SISTEMAS", GRUPO, "Popayán, 2026"):
        par(doc, linea, size=10.5, align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    salto(doc)

    par(doc, "TRABAJO DE GRADO", size=13, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=12)
    par(doc, TITULO, size=12, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=16)
    par(doc, f"Autor: {AUTOR}", size=11, align=WD_ALIGN_PARAGRAPH.CENTER, after=10)
    par(doc, f"Director: {DIRECTOR}", size=11, align=WD_ALIGN_PARAGRAPH.CENTER, after=24)
    for rol in ("Director", "Jurado 1", "Jurado 2"):
        par(doc, f"{rol}: _________________________________________", size=11,
            align=WD_ALIGN_PARAGRAPH.CENTER, after=18)
    par(doc, "Popayán, 20 de noviembre de 2026", size=11,
        align=WD_ALIGN_PARAGRAPH.CENTER, after=6)
    salto(doc)


def dedicatoria_agradecimientos(doc):
    h1(doc, "DEDICATORIA")
    par(doc, "El autor dedica este trabajo a su familia, por el sostén constante durante los "
             "semestres que tomó la investigación, y a los músicos noveles que inspiraron la "
             "pregunta que lo orienta: quienes hacen música sin haber encontrado todavía a su "
             "oyente.")
    salto(doc)
    h1(doc, "AGRADECIMIENTOS")
    par(doc, "El autor agradece al director y al codirector por la lectura crítica de cada "
             "versión del anteproyecto y por las observaciones que dieron forma a la evaluación "
             "final; al grupo de investigación IMS/LOGICIEL por el acompañamiento metodológico; "
             "y a los evaluadores del anteproyecto, cuyas siete observaciones se atendieron una "
             "a una y quedaron registradas en la tabla 2 de este documento.")
    par(doc, "Agradece también a las comunidades que publican los conjuntos de datos abiertos "
             "sobre los que se construyó el catálogo local, y a los proyectos de software libre "
             "que hicieron posible entrenar y desplegar el sistema sin licencias de pago.")
    salto(doc)


def indices(doc):
    h1(doc, "TABLA DE CONTENIDO")
    campo_toc(doc)
    salto(doc)
    h1(doc, "TABLA DE FIGURAS")
    for i, (_, titulo) in enumerate(FIGS, 1):
        p = doc.add_paragraph()
        r = p.add_run(f"Figura {i}. ")
        r.bold = True
        p.add_run(titulo)
        p.paragraph_format.space_after = Pt(2)
    salto(doc)
    h1(doc, "ÍNDICE DE TABLAS")
    for i, titulo in enumerate(TABS, 1):
        p = doc.add_paragraph()
        r = p.add_run(f"Tabla {i}. ")
        r.bold = True
        p.add_run(titulo)
        p.paragraph_format.space_after = Pt(2)
    salto(doc)


def resumen(doc, d):
    t, r = d.get("turnos") or {}, d.get("ranking") or {}
    g = (r.get("agregado_gradado") or {}).get("sistema") or {}
    e = d.get("encuesta") or {}
    h1(doc, "RESUMEN")
    par(doc,
        "La industria musical concentró su consumo en un puñado de artistas visibles: el "
        "reporte global de 2025 documenta un mercado dominado por el streaming y por catálogos "
        "que premian lo ya conocido [26], y la literatura sobre larga cola muestra que los "
        "sistemas de recomendación tienden a reforzar esa concentración en lugar de corregirla "
        "[34], [35]. Frente a ese problema, esta investigación construyó y evaluó EchoPulse AI, "
        "un agente conversacional que recomienda música en español a partir de una arquitectura "
        "enteramente local: una tabla maestra de "
        f"{mil((r.get('insumos') or {}).get('pistas'))} pistas consolidada desde fuentes públicas, "
        "un Transformer de contenido que fusiona letra y rasgos técnicos mediante atención "
        "cruzada, un Transformer de intención conversacional y un modelo de lenguaje pequeño "
        "que redacta la respuesta, todo ejecutándose en dos núcleos de CPU.")
    par(doc,
        "El trabajo siguió un enfoque mixto con fases adaptadas de CRISP-DM [36]. La evaluación "
        f"se realizó sobre {mil(t.get('turnos'))} turnos de conversación en {mil(t.get('sesiones'))} "
        "sesiones contra la demo desplegada, con relevancia derivada del propio catálogo y tres "
        "líneas base. Con ganancia gradada, el sistema alcanzó HR@1 de "
        f"{pc(g.get('hr1'), 3)}, Recall@10 de {pc(g.get('recall10'), 3)}, MRR de {pc(g.get('rr'), 3)} "
        f"y NDCG@10 de {pc(g.get('ndcg10'), 3)}, por encima de popularidad global, coincidencia "
        "léxica y azar en las cuatro métricas y en las tres variantes de relevancia. La tanda "
        f"interna entregó {pc((t.get('diversidad') or {}).get('emergentes_pct'))} % de artistas "
        "emergentes con una latencia mediana de "
        f"{seg((t.get('latencia_servidor_ms') or {}).get('p50'))} s. El instrumento cualitativo "
        f"registró {mil(e.get('validas'))} respuestas completas y se reporta de forma descriptiva, "
        "declarando su baja consistencia interna. Se concluye que la hipótesis se sostiene en el "
        "ranking del sistema y que el corte de la interfaz es el punto donde el descubrimiento "
        "se pierde, lo que define el trabajo futuro.")
    mixto(doc, [("Palabras clave: ", True),
                ("recomendación musical, Transformers, multimodalidad, artistas emergentes, "
                 "diversidad, evaluación por turnos, despliegue en CPU.", False)])
    salto(doc)
    h1(doc, "ABSTRACT")
    par(doc,
        "The music industry concentrated consumption on a handful of visible artists: the 2025 "
        "global report documents a streaming-dominated market whose catalogues reward what is "
        "already known [26], and long-tail research shows that recommender systems tend to "
        "reinforce that concentration rather than correct it [34], [35]. This research built and "
        "evaluated EchoPulse AI, a conversational agent that recommends music in Spanish from a "
        "fully local architecture: a master table of "
        f"{mil((r.get('insumos') or {}).get('pistas'))} tracks consolidated from public sources, a "
        "content Transformer that fuses lyrics and technical features through cross-attention, a "
        "conversational intention Transformer and a small language model that writes the reply, "
        "all running on two CPU cores.")
    par(doc,
        "The work followed a mixed-methods approach with phases adapted from CRISP-DM [36]. "
        f"Evaluation used {mil(t.get('turnos'))} conversation turns across {mil(t.get('sesiones'))} "
        "sessions against the deployed demo, with catalogue-derived relevance and three baselines. "
        f"With graded gain the system reached HR@1 of {pc(g.get('hr1'), 3)}, Recall@10 of "
        f"{pc(g.get('recall10'), 3)}, MRR of {pc(g.get('rr'), 3)} and NDCG@10 of {pc(g.get('ndcg10'), 3)}, "
        "above global popularity, lexical matching and chance on all four metrics and all three "
        f"relevance variants. The internal list delivered {pc((t.get('diversidad') or {}).get('emergentes_pct'))} % "
        f"emerging artists with a median latency of {seg((t.get('latencia_servidor_ms') or {}).get('p50'))} s. "
        f"The qualitative instrument recorded {mil(e.get('validas'))} complete responses and is "
        "reported descriptively, declaring its low internal consistency. The hypothesis holds at "
        "the ranking level; the interface cut is where discovery is lost, which defines future work.")
    mixto(doc, [("Keywords: ", True),
                ("music recommendation, Transformers, multimodality, emerging artists, diversity, "
                 "turn-level evaluation, CPU deployment.", False)])
    salto(doc)


def introduccion(doc, d):
    t = d.get("turnos") or {}
    h1(doc, "INTRODUCCIÓN")
    par(doc,
        "Escuchar música dejó de ser una decisión de compra para convertirse en una decisión "
        "de descubrimiento: quien abre una aplicación de streaming no elige entre discos, sino "
        "entre listas que un algoritmo ordenó por él. Esa mediación tiene un efecto documentado "
        "sobre qué artistas llegan a ser escuchados [26], [34]. Los sistemas que ordenan esas "
        "listas aprenden de lo que ya se escucha, y por eso tienden a devolver lo mismo que "
        "consagró la audiencia: el sesgo de popularidad no es un defecto ocasional sino una "
        "propiedad estructural del aprendizaje a partir de interacciones [13], [14], [35].")
    par(doc,
        "Este trabajo nació de una pregunta práctica con consecuencia investigativa: si un "
        "recomendador se construye desde la afinidad de contenido —letra, rasgos de audio y "
        "ánimo— en lugar de desde la popularidad, ¿puede abrir espacio a músicos noveles sin "
        "degradar la pertinencia de lo que propone? La respuesta exigía tres cosas que hasta "
        "ahora no existían juntas en un mismo artefacto verificable: datos musicales "
        "consolidados localmente, modelos entrenados sobre ellos y una evaluación con métricas "
        "de orden calculadas sobre conversaciones reales del sistema desplegado.")
    par(doc,
        "El documento presenta el recorrido completo. El capítulo 1 delimita el problema, "
        "justifica la investigación, declara sus aportes y fija objetivos y metodología. El "
        "capítulo 2 reúne los conceptos necesarios y revisa críticamente el estado del arte. "
        "El capítulo 3 describe la arquitectura implementada, módulo por módulo, con sus "
        "diagramas. El capítulo 4 documenta la consolidación de datos, el entrenamiento de los "
        "dos Transformers y el despliegue continuo y gratuito. El capítulo 5 reporta la "
        f"evaluación sobre {mil(t.get('turnos'))} turnos: métricas de orden frente a líneas base, "
        "robustez del protocolo, diversidad, coherencia de la promesa, latencia y el instrumento "
        "cualitativo. El capítulo 6 concluye por objetivo y plantea el trabajo futuro. Cierran "
        "las referencias verificadas y cuatro anexos de reproducibilidad.")
    par(doc,
        "Dos decisiones de honestidad metodológica atraviesan todo el texto. Primera: la unidad "
        "de análisis es el turno de conversación y la sesión, no el visitante; el corpus se "
        "generó contra la demo pública y así se declara. Segunda: ninguna cifra se escribe de "
        "memoria; cada tabla y figura sale de un registro o de un cálculo reproducible, y lo que "
        "no pudo medirse se dice en voz alta en lugar de estimarse.")
    salto(doc)


# ---------------------------------------------------------- capítulo 1 --

def cap1(doc, d):
    h1(doc, "CAPÍTULO 1. ASPECTOS GENERALES DE LA INVESTIGACIÓN")
    h2(doc, "1.1 Planteamiento del problema")
    par(doc,
        "El consumo musical mundial se organiza hoy alrededor del streaming: el reporte global "
        "de la industria correspondiente a 2025 sitúa a la suscripción y al consumo en línea como "
        "el eje del ingreso sectorial [26]. Ese modelo concentra la atención en catálogos "
        "visibles y deja fuera a la mayoría de quienes publican música. La literatura sobre la "
        "larga cola describió el fenómeno hace más de una década: la distribución digital "
        "prometía exposición para todos, pero los mecanismos de descubrimiento reprodujeron la "
        "concentración del mercado físico [34]. Los estudios recientes sobre recomendación "
        "musical confirman que el sesgo de popularidad y la falta de diversidad siguen siendo "
        "desafíos abiertos del área [35].")
    par(doc,
        "Las causas son técnicas y están identificadas. Los recomendadores secuenciales "
        "aprenden de historiales de interacción, que sobrerrepresentan a los artistas ya "
        "conocidos [3], [4]; los objetivos de entrenamiento optimizan aciertos sobre ese mismo "
        "sesgo; y las políticas de orden premian la popularidad como señal de calidad "
        "[13], [25]. A ello se suma una causa de infraestructura: los sistemas conversacionales "
        "recientes dependen de modelos de lenguaje y de índices alojados en servicios de pago, "
        "lo que deja fuera a investigadores y músicos sin presupuesto [27], [29].")
    par(doc,
        "Varios trabajos han intentado cerrar esa brecha. SASRec introdujo la autoatención "
        "sobre secuencias de interacción [3] y BERT4Rec la versión bidireccional enmascarada "
        "[4]; ambos mejoran la precisión pero heredan el sesgo del historial. TalkPlay y "
        "TalkPlay-Tools llevan la recomendación musical al terreno conversacional con modelos "
        "de lenguaje [27], [33]; MuseChat la ancla a contenido de video [28]; InteRecAgent, "
        "Agent4Rec y AgentCF exploran agentes autónomos que recomiendan [29], [30], [31]. En "
        "paralelo, la línea de diversidad por diseño muestra que diversificar puede hacerse "
        "sin perder utilidad percibida [15], [32].")
    par(doc,
        "Las propuestas existentes comparten tres desventajas: dependen de historiales de "
        "interacción que no existen para un artista novel, delegan la conversación y el índice "
        "en servicios externos de pago, y evalúan la diversidad como métrica secundaria sin "
        "medir el descubrimiento en el punto donde el oyente lo ve. Por esa razón esta "
        "investigación se centra en un recomendador local, guiado por contenido y conversacional, "
        "cuya diversidad se mide en la tanda entregada y no solo en el ranking interno.")
    par(doc,
        "La hipótesis que se sigue de los avances en atención y fusión multimodal [1], [16] es "
        "que un espacio de embeddings aprendido desde letra y rasgos de audio permite ordenar "
        "por afinidad sin necesitar popularidad, y que un módulo de intención conversacional "
        "puede reordenar ese espacio sin destruir la pertinencia. En este trabajo se busca "
        "construir ese sistema y evaluarlo con métricas de orden, diversidad y latencia frente "
        "a líneas base, sobre turnos de conversación del sistema desplegado. La pregunta que "
        "orienta la investigación es:")
    par(doc, PREGUNTA, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=10)

    h2(doc, "1.2 Justificación")
    par(doc,
        "La conveniencia de la investigación está en que resuelve un problema real de "
        "descubrimiento con un artefacto que cualquiera puede usar y auditar: la demo es "
        "pública, el código está versionado y el catálogo es local. Su relevancia social "
        "alcanza a músicos noveles y a oyentes que reciben listas cada vez más parecidas; "
        "diversificar el descubrimiento amplía el acceso a audiencia sin exigir presupuesto de "
        "promoción [15], [32].")
    par(doc,
        "Las implicaciones prácticas son inmediatas: el sistema conversa en español, funciona "
        "en dos núcleos de CPU y no requiere servicios de pago, de modo que una institución "
        "educativa o un colectivo musical puede replicarlo. El valor teórico está en mostrar "
        "que la afinidad de contenido multimodal sostiene métricas de orden competitivas sin "
        "señal de popularidad, y en documentar con evidencia dónde se pierde el descubrimiento "
        "entre el ranking y la interfaz. La utilidad metodológica queda en el protocolo de "
        "relevancia derivada del catálogo, con tres variantes y análisis de sensibilidad, y en "
        "un cliente de evaluación que registra cada turno con su ranking completo: ambos "
        "instrumentos son reutilizables por otros trabajos del área.")

    h2(doc, "1.3 Aportes de la investigación")
    viñetas(doc, [
        ("Monografía. ", "Este documento, que consolida el anteproyecto, las versiones previas "
         "del sistema y la evaluación final en un solo texto verificable."),
        ("Aplicación pública. ", "La demo desplegada de forma continua y gratuita, con enlace "
         "HTTPS estable de respaldo, sobre la que se generó y midió todo el corpus."),
        ("Arquitectura local reproducible. ", "Tabla maestra, índice de fama, dos Transformers "
         "entrenados y su procedimiento de entrenamiento documentado con las salidas reales."),
        ("Protocolo e instrumentos de evaluación. ", "Relevancia derivada del catálogo con tres "
         "variantes y sensibilidad, tres líneas base, cliente de turnos y evaluador de ranking."),
        ("Instrumento cualitativo publicado. ", "Formulario de veinte ítems enlazado desde la "
         "demo, con su exportación y su análisis descriptivo completo."),
        ("Artículo y registro. ", "El material queda dispuesto para artículo de investigación y "
         "para registro de software; el trámite de registro es trabajo futuro declarado."),
    ])

    h2(doc, "1.4 Objetivos")
    h3(doc, "1.4.1 Objetivo general")
    par(doc, OBJ_GENERAL)
    h3(doc, "1.4.2 Objetivos específicos")
    for i, o in enumerate(OBJ_ESPECIFICOS, 1):
        par(doc, f"O.E.{i}. {o}")

    h2(doc, "1.5 Metodología")
    par(doc,
        "El proyecto se abordó con enfoque mixto. La mitad cuantitativa mide orden, diversidad, "
        "coherencia y latencia sobre turnos registrados; la mitad cualitativa recoge percepción "
        "mediante un formulario de veinte afirmaciones en escala de cinco puntos más comentario "
        "libre. El desarrollo siguió fases adaptadas de CRISP-DM, el proceso estándar "
        "interindustrias para minería de datos [36]: comprensión y preparación de datos, "
        "modelado y evaluación, y despliegue con divulgación. Cada fase se corresponde con un "
        "objetivo específico y deja una evidencia verificable, que es la columna final de la "
        "tabla 1.")
    tab(doc, 1,
        ["Fase", "Objetivo", "Actividades", "Herramientas y métodos", "Resultado esperado y alcanzado"],
        [
            ["F1 · Comprensión y preparación", "O.E.1",
             "Revisión del estado del arte; unión de fuentes; limpieza; cuantiles de ánimo; índice de fama.",
             "pandas, pyarrow, ETL propio; revisión crítica agrupada por líneas.",
             "Tabla maestra de 5.710 pistas × 48 columnas e índice de fama de 545.983 entradas."],
            ["F2 · Modelado", "O.E.2",
             "Entrenamiento del Transformer de contenido y del de intención; validación aislada.",
             "PyTorch [20], GPU para M2 y CPU para validar M3; AdamW [18].",
             "MSE 0,0289 → 0,0002 en 15 épocas; M3 sobre 38.343 clases con MRR medido."],
            ["F3 · Evaluación y despliegue", "O.E.3",
             "Despliegue continuo; corrida de turnos; métricas frente a líneas base; instrumento cualitativo.",
             "Docker Compose, túneles HTTPS, cliente de evaluación, evaluador de ranking.",
             "333 turnos medidos; HR@1, Recall@10, MRR y NDCG@10 sobre tres variantes."],
            ["F4 · Divulgación", "Transversal",
             "Monografía, artículo, figuras y anexos de reproducibilidad.",
             "Constructores de documento por script; bibliografía verificada.",
             "Este documento y el informe con formato Anexo 3, con cifras reproducibles."],
        ],
        anchos=[3.0, 1.6, 4.4, 3.6, 4.2], size=8)
    par(doc,
        "El anteproyecto fue aprobado con recomendaciones y una calificación promedio de 3,8 "
        "sobre 5. Las siete observaciones del evaluador se atendieron de forma explícita; la "
        "tabla 2 registra cada una y el lugar de este documento donde queda resuelta.")
    tab(doc, 2,
        ["Observación del evaluador", "Atención en este trabajo"],
        [
            ["Sección explícita de resultados esperados alineada con objetivos.",
             "Tabla 18 y capítulo 5: cada objetivo tiene su medición."],
            ["Definir con precisión el tipo de datos (audio, texto, emociones, metadata).",
             "§4.1 y §4.2: fuentes, columnas, seis rasgos de ánimo y veintiséis técnicos."],
            ["Definir métricas de evaluación (precision, recall, NDCG, etc.).",
             "§5.1 y anexo B: HR@1, HR@3, Recall@10, MRR y NDCG@10 con variantes."],
            ["Especificar la arquitectura Transformer y la integración multimodal.",
             "§3.2 y §3.3 con figuras 2 y 3: dimensiones, cabezas, capas y atención cruzada."],
            ["Fortalecer el estado del arte con análisis crítico.",
             "§2.2: tres líneas, brecha por trabajo y brecha común."],
            ["Articular objetivos específicos con la metodología.",
             "Tabla 1: fase, objetivo, actividad, herramienta y evidencia."],
            ["Revisar normas de citación y actualidad de fuentes.",
             "Referencias IEEE verificadas una a una; depuración en anexo A."],
        ],
        anchos=[7.4, 9.4], size=8.5)

    h2(doc, "1.6 Organización del documento")
    par(doc,
        "El capítulo 2 presenta el marco conceptual y el estado del arte. El capítulo 3 "
        "describe la arquitectura y los métodos del sistema con sus diagramas. El capítulo 4 "
        "documenta datos, entrenamiento, despliegue y correcciones. El capítulo 5 reporta la "
        "evaluación completa. El capítulo 6 concluye y plantea trabajo futuro. Las referencias "
        "cierran el cuerpo y los anexos A a D garantizan la reproducibilidad de cifras, "
        "protocolo y artefactos.")
    salto(doc)


# ---------------------------------------------------------- capítulo 2 --

def cap2(doc, d):
    h1(doc, "CAPÍTULO 2. MARCO DE REFERENCIA")
    h2(doc, "2.1 Marco teórico-conceptual")
    h3(doc, "2.1.1 Sistema de recomendación y sesgo de popularidad")
    par(doc,
        "Un sistema de recomendación ordena un catálogo para un usuario según una señal de "
        "preferencia; las familias clásicas son filtrado colaborativo, basado en contenido e "
        "híbridos [23], [24]. Cuando la señal es el historial de interacciones, el sistema "
        "aprende también la distribución de popularidad del catálogo: los ítems frecuentes "
        "dominan el entrenamiento y el resultado refuerza su propia frecuencia. Ese círculo es "
        "el sesgo de popularidad, y la literatura lo trata como problema de equidad de "
        "exposición además de problema de precisión [13], [14], [34].")
    h3(doc, "2.1.2 Recomendación conversacional")
    par(doc,
        "La recomendación conversacional reemplaza el perfil estático por un diálogo: el "
        "sistema pregunta, interpreta y refina turno a turno. Los enfoques recientes usan "
        "modelos de lenguaje como planificadores que llaman herramientas de recuperación "
        "[27], [29], [33]. La diferencia con un buscador es que el estado de la conversación "
        "—lo pedido, lo descartado, lo heredado— forma parte de la consulta.")
    h3(doc, "2.1.3 Multimodalidad y representación del ánimo")
    par(doc,
        "La multimodalidad combina fuentes heterogéneas —texto, audio, metadatos— en una "
        "representación común; la taxonomía de Baltrušaitis distingue representación, "
        "traducción, alineación, fusión y coaprendizaje [16]. Este trabajo usa fusión: la letra "
        "y los rasgos técnicos se integran dentro de la atención del Transformer. El ánimo se "
        "modela con el modelo circumplejo de Russell, que organiza el afecto en valencia y "
        "activación [17]; operativamente se expresa como cuantiles de energía, bailabilidad, "
        "valencia, tristeza, romanticismo y sonoridad.")
    h3(doc, "2.1.4 Transformer y atención")
    par(doc,
        "El Transformer sustituye la recurrencia por autoatención: cada posición consulta a "
        "todas las demás mediante productos escalares escalados, con cabezas múltiples que "
        "atienden subespacios distintos [1]. La atención cruzada permite que una secuencia "
        "consulte a otra, que es el mecanismo usado aquí para condicionar la letra por lo "
        "técnico. BERT mostró el valor del preentrenamiento bidireccional enmascarado [2], y "
        "SASRec y BERT4Rec trasladaron la autoatención a la recomendación secuencial [3], [4].")
    h3(doc, "2.1.5 Embeddings, recuperación y generación aumentada")
    par(doc,
        "Un embedding es un vector denso que representa una pieza de contenido; la similitud "
        "coseno entre vectores ordena por afinidad. Recuperar candidatas y luego generar una "
        "respuesta condicionada por ellas es el patrón de generación aumentada por recuperación "
        "[9], [10]: el modelo de lenguaje no inventa el catálogo, lo comenta.")
    h3(doc, "2.1.6 Métricas de orden y diversidad")
    par(doc,
        "HR@k mide si alguna posición de las primeras k es relevante; Recall@k, la fracción del "
        "conjunto relevante cubierta; MRR, el inverso del rango del primer acierto; y "
        "NDCG@k, la ganancia acumulada descontada por posición, normalizada por el orden ideal "
        "[12]. La diversidad se mide aquí como artistas y géneros distintos por tanda y como "
        "fracción de artistas emergentes, en la línea de los objetivos más allá de la precisión "
        "[14], [15].")
    h3(doc, "2.1.7 Inferencia en CPU y cuantización")
    par(doc,
        "Ejecutar modelos en CPU sin GPU exige reducir precisión y concurrencia: la "
        "cuantización a enteros o a formatos de pocos bits conserva calidad con una fracción "
        "del costo [19]. El despliegue de este trabajo usa un modelo de lenguaje cuantizado y "
        "un único slot de generación, decisión que la evaluación de latencia cuantifica.")

    h2(doc, "2.2 Estado del arte")
    par(doc,
        "Los trabajos que abordan el problema se agrupan en tres líneas. La primera aprende "
        "orden desde interacciones: SASRec [3] y BERT4Rec [4] establecieron la autoatención "
        "secuencial como referencia de precisión, y los sistemas industriales a gran escala "
        "mostraron su valor de negocio [25]. Su desventaja común es que necesitan historial: "
        "para un artista sin interacciones no hay señal que aprender. La segunda línea lleva "
        "la recomendación al diálogo con modelos de lenguaje: TalkPlay [27] y TalkPlay-Tools "
        "[33] sobre música, MuseChat [28] sobre video, e InteRecAgent [29], Agent4Rec [30] y "
        "AgentCF [31] como agentes generales. Su desventaja común es la dependencia de "
        "servicios externos y la evaluación centrada en la calidad del diálogo más que en el "
        "descubrimiento medible. La tercera línea estudia la diversidad como objetivo de "
        "diseño: diversificación por tópicos [13], diversidad por diseño en música [15] y "
        "estudios longitudinales de su efecto en el oyente [32]. Su desventaja es que la "
        "diversidad se mide como métrica agregada y rara vez en el punto de corte que el "
        "usuario ve.")
    tabla(doc,
          ["Trabajo", "Aporte", "Brecha frente a esta investigación"],
          [
              ["SASRec [3]", "Autoatención secuencial para ordenar interacciones.",
               "Requiere historial; sin señal para artistas noveles."],
              ["BERT4Rec [4]", "Preentrenamiento bidireccional enmascarado sobre secuencias.",
               "Hereda el sesgo de popularidad del historial."],
              ["Netflix [25]", "Evidencia industrial del valor del recomendador.",
               "Optimiza engagement, no descubrimiento; infraestructura de pago."],
              ["TalkPlay / Tools [27], [33]", "Recomendación musical conversacional con LLM.",
               "Dependencia de servicios externos; diversidad no medida en el corte visible."],
              ["MuseChat [28]", "Conversación anclada a contenido de video.",
               "Dominio distinto; sin catálogo local ni métricas de orden públicas."],
              ["Agentes [29], [30], [31]", "LLM como planificador y simulador de usuarios.",
               "Costo de inferencia y evaluación centrada en el diálogo."],
              ["Diversidad [13], [15], [32]", "Diversificar sin perder utilidad percibida.",
               "Métrica agregada; no mide qué ve el oyente tras el corte de interfaz."],
          ],
          anchos=[3.6, 6.0, 7.2], size=8.5,
          caption="Tabla de trabajos relacionados: aporte y brecha.")
    par(doc,
        "La brecha común es la ausencia de un sistema conversacional musical que sea local y "
        "auditable, que ordene por afinidad de contenido sin señal de popularidad, y que mida "
        "el descubrimiento tanto en el ranking como en la tanda visible, con métricas de orden "
        "frente a líneas base. Este trabajo se sitúa exactamente ahí.")
    salto(doc)


# ---------------------------------------------------------- capítulo 3 --

def cap3(doc, d):
    t = d.get("turnos") or {}
    h1(doc, "CAPÍTULO 3. ARQUITECTURA Y MÉTODOS DEL SISTEMA")
    h2(doc, "3.1 Vista general del agente")
    par(doc,
        "EchoPulse AI conversa en español y opera en cuatro tiempos: entender la petición, "
        "recuperar candidatas por contenido, reordenarlas con intención y reglas verificables, "
        "y redactar una respuesta validada que nombre exactamente lo que la pantalla muestra. "
        "La figura 1 recorre el pipeline completo de un turno, con los servicios transversales "
        "que aplican a todos: registro del evento, memoria de sesión y limitador por dirección.")
    fig(doc, 1)
    par(doc,
        "El Módulo 2 recupera treinta candidatas combinando similitud coseno entre el embedding "
        "de la consulta y el de cada pista con coincidencia léxica de Jaccard sobre la letra y "
        "con el perfil de género y ánimo. El Módulo 3 reordena esas treinta con su Transformer "
        "de intención. Sobre la mezcla actúan reglas de diversidad y de coherencia, y el corte "
        "final entrega diez tarjetas internas de las cuales tres se muestran como destacadas.")

    h2(doc, "3.2 Módulo 2: Transformer de contenido")
    par(doc,
        "El Transformer de contenido fusiona dos modalidades dentro de la atención. La letra "
        "se tokeniza con un vocabulario de "
        f"{mil((d.get('notebooks') or {}).get('vocabulario'))} palabras y se proyecta a un "
        "embedding de dimensión 512 con codificación posicional aprendida; los veintiséis "
        "rasgos técnicos se proyectan a la misma dimensión. Un decodificador de seis capas con "
        "ocho cabezas atiende la letra condicionada por lo técnico mediante atención cruzada: "
        "la letra actúa como consulta y lo técnico como clave. La figura 2 muestra el esquema.")
    fig(doc, 2)
    par(doc,
        "El resultado es un embedding de contenido por pista, de 512 dimensiones, que alimenta "
        "el índice local sobre el que se calcula la similitud coseno en línea. La recuperación "
        "no consulta ninguna API externa: el índice y los pesos viven en la misma máquina que "
        "sirve la conversación.")

    h2(doc, "3.3 Módulo 3: Transformer de intención")
    par(doc,
        "El Módulo 3 es un Transformer de intención conversacional de dimensión 256, cuatro "
        "capas, ocho cabezas y feed-forward de 1024, entrenado sobre las clases de canción de "
        "TalkPlayData 2. Recibe el diálogo traducido a inglés, lo tokeniza con longitud máxima "
        "512 y produce una probabilidad por clase de canción. La figura 3 resume su esquema y "
        "su evidencia.")
    fig(doc, 3)
    par(doc,
        "La fusión con el Módulo 2 es explícita y auditable: 0,70 de similitud de contenido más "
        "0,30 de intención. Las candidatas que el Módulo 3 conoce se normalizan por su máximo; "
        "las que no existen como clase reciben la mediana de las conocidas, un valor neutro que "
        "ni premia ni castiga, y quedan marcadas. El sistema registra por turno la cobertura "
        "del Módulo 3 sobre la tanda, de modo que una tanda sin reordenamiento tiene causa "
        "visible en el registro y no queda como misterio.")

    h2(doc, "3.4 Reglas de tanda, diversidad y coherencia")
    par(doc,
        "Sobre la mezcla actúan tres reglas verificables. Primera, castigo multiplicativo por "
        "desvío de ánimo, ×(1 − 0,60 × desvío), y por desvío de género, ×(1 − 0,50 × desvío), "
        "medidos en cuantiles del catálogo. Segunda, máximo dos pistas por artista, con "
        "relajación progresiva a cinco y luego sin tope si el pool no alcanza. Tercera, cuota "
        "de artistas emergentes: de las diez posiciones de la tanda, siete se reservan para "
        "artistas sin señal de fama y tres se garantizan para reconocidos, de modo que el "
        "descubrimiento no dependa del azar del orden. Las pistas sin título real se descartan "
        "antes de llenar la tanda.")
    par(doc,
        "El perfil de género y ánimo se hereda entre turnos cuando el oyente no lo repite: "
        "«dame más de esa energía» conserva el género del turno anterior y cambia solo el "
        "ánimo. Las pistas ya recomendadas en la sesión se excluyen de la recuperación, lo que "
        "evita repetir la misma tanda en turnos consecutivos.")

    h2(doc, "3.5 Voz conversacional y cadena de validación")
    par(doc,
        "La voz la produce un modelo de lenguaje Qwen de 1,5 mil millones de parámetros, "
        "cuantizado y servido en la misma máquina virtual, con temperatura 0,5 y contexto de "
        "4096 tokens. Su salida no se publica tal cual: pasa por una cadena de ocho controles "
        "—corrección de parejas artista-canción, descarte de citas ajenas a la tanda, limpieza "
        "de ecos de la lista interna, eliminación de numeraciones, recorte de frases, cierre de "
        "comillas colgadas, comprobación de que el texto es aprovechable y garantía de que la "
        "tanda real queda citada— y termina con una pregunta que invita a continuar.")
    par(doc,
        "Si la cadena devuelve vacío, el orquestador descarta lo escrito por el modelo y usa "
        "un motor determinista que nombra canciones reales de la tanda y cierra con pregunta. "
        "En ningún caso se reintroduce el texto crudo del modelo. La voz y las tarjetas "
        "visibles son siempre la misma tanda, para que lo que el agente dice y lo que la "
        "pantalla muestra no diverjan.")

    h2(doc, "3.6 Interfaz y experiencia de uso")
    par(doc,
        "La interfaz muestra tres tarjetas destacadas con nombre real de canción y artista, "
        "género, enlaces de escucha y una explicación breve; nunca muestra identificadores "
        "internos de pista. El pie de cada tanda enlaza el instrumento cualitativo de la "
        "investigación. La entrada admite texto y voz, y la respuesta se lee en español con la "
        "misma tanda que la pantalla. Estas decisiones de presentación son parte del método: "
        "la evaluación mide precisamente la distancia entre lo que el ranking ordena y lo que "
        "el oyente llega a ver.")
    salto(doc)


# ---------------------------------------------------------- capítulo 4 --

def cap4(doc, d):
    nb = d.get("notebooks") or {}
    it = nb.get("intencion") or {}
    ins = (d.get("ranking") or {}).get("insumos") or {}
    perdida = nb.get("perdida") or []
    h1(doc, "CAPÍTULO 4. DATOS, ENTRENAMIENTO Y DESPLIEGUE")
    h2(doc, "4.1 Fuentes y consolidación")
    par(doc,
        "Cuatro fuentes públicas alimentaron el sistema, con papeles distintos. El Million "
        "Song Dataset aportó descriptores de audio y metadatos [5]; WASABI aportó análisis "
        "cultural, de letra y de audio sobre dos millones de canciones comerciales [6]; el "
        "conjunto Lyrics 1950-2019 aportó letras limpias con ventana temporal amplia [7]; y "
        "TalkPlayData 2 aportó conversaciones sintéticas oyente-música para el módulo de "
        "intención [8]. Esta última no se mezcla con el catálogo de recomendación: corregir "
        "esa separación fue una de las correcciones de las primeras versiones del documento, "
        "que presentaban a TalkPlayData 2 como parte de la tabla maestra.")
    fig(doc, 4)
    tab(doc, 3,
          ["Fuente", "Qué aporta", "Papel en el sistema"],
          [
              ["Million Song Dataset [5]", "Descriptores de audio y metadatos de un millón de pistas.",
               "Rasgos técnicos de la tabla maestra."],
              ["WASABI [6]", "Análisis cultural, de letra y de audio de dos millones de canciones.",
               "Géneros, ánimo y metadatos de la tabla maestra."],
              ["Lyrics 1950-2019 [7]", "Letras limpias con ventana temporal amplia.",
               "Modalidad lírica del Transformer de contenido."],
              ["TalkPlayData 2 [8]", "Diálogos sintéticos oyente-música.",
               "Entrenamiento del Módulo 3; fuera del catálogo."],
          ],
          anchos=[4.2, 6.4, 6.2], size=8.5)
    par(doc,
        "La unión sobrevivió en una tabla maestra de "
        f"{mil(ins.get('pistas'))} pistas y cuarenta y ocho columnas, en formato columnar con "
        "particiones de entrenamiento, validación y prueba. El proceso de unión, limpieza y "
        "normalización quedó versionado como cuadernos ETL, de modo que la tabla puede "
        "reconstruirse desde las fuentes.")

    h2(doc, "4.2 Rasgos, vocabulario e índice de fama")
    par(doc,
        "Sobre la tabla se calcularon seis rasgos de ánimo —energía, bailabilidad, valencia, "
        "tristeza, romanticismo y sonoridad— expresados como cuantiles por columna, lo que "
        "permite medir desvíos entre lo pedido y lo entregado en una escala común. El vector "
        "técnico de entrada tiene veintiséis componentes y el vocabulario del tokenizador de "
        f"letras quedó en {mil(nb.get('vocabulario'))} palabras con frecuencia mínima de dos.")
    par(doc,
        "El índice de fama reúne "
        f"{mil(545983)} entradas de artista y título con su popularidad, más la popularidad "
        "máxima por artista. Una pista se considera reconocida si su popularidad —de canción "
        "o de artista— alcanza el umbral de 60, o si figura como clásica en WASABI; sin "
        "ninguna de esas señales se marca como emergente. En el catálogo consolidado, "
        f"{mil((ins.get('popularidad') or {}).get('con_popularidad'))} de "
        f"{mil(ins.get('pistas'))} pistas tienen señal de popularidad y "
        f"{mil((ins.get('pistas') or 0) - ((ins.get('popularidad') or {}).get('con_popularidad') or 0))} "
        "carecen de ella. Esa señal, derivada del propio catálogo, es la que permite priorizar "
        "descubrimiento sin depender de una API externa ni de sus cuotas.")

    h2(doc, "4.3 Entrenamiento del Módulo 2")
    par(doc,
        f"El Transformer de contenido se entrenó durante {mil(nb.get('epocas') or len(perdida))} "
        "épocas con lote de 32 y 179 lotes por época, en GPU. La pérdida MSE cayó de "
        f"{nm(perdida[0], 4) if perdida else '—'} en la primera época a "
        f"{nm(perdida[-1], 4) if perdida else '—'} en la última: dos órdenes de magnitud, con "
        "meseta a partir de la época doce. La figura 5 muestra la curva en escala logarítmica; "
        "la tabla 4 resume los hiperparámetros.")
    fig(doc, 5)
    tab(doc, 4,
          ["Hiperparámetro", "Valor", "Evidencia"],
          [
              ["d_model · cabezas · capas", "512 · 8 · 6", "Definición del modelo en app.py."],
              ["max_len · vocabulario", "151 · 9.880", "Tokenizador de letras (frecuencia ≥ 2)."],
              ["Lote · lotes por época", "32 · 179", "Salida del cuaderno de entrenamiento."],
              ["Épocas · dispositivo", "15 · GPU (cuda)", "Registro de épocas del cuaderno."],
              ["Pérdida MSE inicial → final",
               f"{nm(perdida[0], 4) if perdida else '—'} → {nm(perdida[-1], 4) if perdida else '—'}",
               "Curva de la figura 5."],
          ],
          anchos=[5.0, 4.4, 7.4], size=8.5)

    h2(doc, "4.4 Entrenamiento y validación del Módulo 3")
    par(doc,
        "El Transformer de intención se entrenó sobre TalkPlayData 2 con AdamW [18], tasa de "
        f"aprendizaje 1e-4, lote 32 y paciencia 5, sobre {mil(it.get('clases'))} clases de "
        f"canción. Su validación aislada sobre {mil(it.get('muestras'))} muestras en CPU arrojó "
        f"MRR de {nm(it.get('mrr'), 4)}, HR@1 de {nm(it.get('hr1'), 2)} %, HR@5 de "
        f"{nm(it.get('hr5'), 2)} % y HR@10 de {nm(it.get('hr10'), 2)} %. La tabla 5 pone esas "
        "cifras frente a la referencia correcta: el azar sobre el mismo número de clases.")
    fig(doc, 6)
    clases = float(it.get("clases") or 1)
    azar1, azar10 = 100.0 / clases, 100.0 * min(10.0, clases) / clases
    tab(doc, 5,
          ["Medida", "Módulo 3", "Azar sobre 38.343 clases", "Lectura"],
          [
              ["HR@1", f"{nm(it.get('hr1'), 2)} %", f"{nm(azar1, 4)} %",
               f"{mil((it.get('hr1') or 0) / azar1)} veces la probabilidad de azar."],
              ["HR@10", f"{nm(it.get('hr10'), 2)} %", f"{nm(azar10, 3)} %",
               f"{mil((it.get('hr10') or 0) / azar10)} veces la probabilidad de azar."],
              ["MRR", nm(it.get("mrr"), 4), "—",
               "Señal débil en aislamiento; aporta sobre 30 candidatas ya afines."],
          ],
          anchos=[3.0, 3.0, 4.4, 6.4], size=8.5, der=(1, 2))
    par(doc,
        "Leer esas cifras exige el contexto correcto: en aislamiento, sobre todo el catálogo "
        "de clases, el módulo es débil; su papel en el agente es reordenar treinta candidatas "
        "que el Módulo 2 ya volvió afines por contenido, y ahí su aporte del 30 % de la mezcla "
        "se vuelve medible, como muestra el capítulo 5.")

    h2(doc, "4.5 Despliegue continuo y gratuito")
    par(doc,
        "El sistema completo vive en una máquina virtual Standard_B2as_v2 de dos núcleos "
        "virtuales y 7,9 GiB de memoria, con cuatro contenedores: la aplicación Flask con los "
        "dos Transformers, el servidor del modelo de lenguaje, y dos túneles HTTPS que "
        "publican la demo sin abrir puertos entrantes. La figura 7 muestra el esquema y la "
        "tabla 6 la decisión de diseño detrás de cada servicio.")
    fig(doc, 7)
    tab(doc, 6,
          ["Servicio", "Papel", "Decisión de diseño"],
          [
              ["app", "Orquestador Flask + M2 + M3 + validador, puerto 7860.",
               "Hilos de BLAS fijados a 1 para no pelear con los 2 núcleos; UID sin privilegios."],
              ["qwen", "llama.cpp server con Qwen2.5-1.5B GGUF Q4_K_M, puerto 8080.",
               "Cuantización [19], ctx 4096, 2 hilos y un solo slot: la CPU no da para más."],
              ["tunnel-cf", "cloudflared: HTTPS público sin dominio propio.",
               "El TLS termina fuera de la VM; la VM solo hace conexiones salientes."],
              ["tunnel", "ngrok con enlace fijo de respaldo.",
               "URL estable para citar; el token vive solo en el entorno de la VM."],
          ],
          anchos=[2.6, 6.4, 7.8], size=8.5)
    par(doc,
        "Un limitador de ventana corta en doce turnos por minuto por dirección de origen "
        "protege los dos núcleos. Las credenciales nunca viajan con el código: el token del "
        "túnel y el de Hugging Face residen en archivos de entorno con permisos restringidos "
        "dentro de la máquina, fuera del repositorio; la clave de administración se usa solo "
        "desde el equipo del autor. Cada redespliegue va precedido de respaldo del código y "
        "reconstruye únicamente el servicio de aplicación, sin detener el resto. Estas "
        "decisiones sostuvieron la demo en línea durante semanas mientras se iteraba.")

    h2(doc, "4.6 Correcciones de la etapa final y pruebas")
    par(doc,
        "La etapa final cerró con una ronda de correcciones verificadas por pruebas. La más "
        "importante afectaba al validador de citas: descartaba toda frase que no contuviera "
        "una cita de la lista, lo que borraba la prosa legítima del modelo y enviaba el turno "
        "al motor determinista. La corrección invirtió el criterio —una frase se descarta solo "
        "si todas sus citas son ajenas a la tanda— y se acompañó de una prueba de regresión "
        "que exige que la prosa sin citas sobreviva y que la tanda real quede citada. La "
        "suite completa quedó en veintisiete pruebas en verde. La tabla 7 lista las "
        "correcciones y su verificación.")
    tab(doc, 7,
          ["Corrección", "Síntoma que resolvía", "Verificación"],
          [
              ["Validador de citas conservaba solo frases con cita",
               "La prosa del modelo se borraba y el turno caía al motor determinista.",
               "Prueba de regresión dedicada; suite de 27 pruebas en verde."],
              ["Nombres reales en lugar de identificadores",
               "Tarjetas y voz mostraban códigos de pista.",
               "Conteo de tarjetas sin nombre: cero en el corpus."],
              ["Eco del prompt traducido a lenguaje hablado",
               "La voz repetía la plantilla interna de la consulta.",
               "Validador de ecos y prueba de turno completo."],
              ["Herencia de perfil entre turnos",
               "«Dame más de esa energía» perdía el género anterior.",
               "Registro de perfil heredado por turno (§5.6)."],
              ["Exclusión de pistas sin nombre",
               "Tarjetas vacías o con título desconocido.",
               "Conteo de tarjetas sin nombre: cero (§5.5)."],
              ["Encuesta enlazada en la demo y en el pie de cada tanda",
               "El instrumento no era alcanzable desde la interfaz.",
               "Enlace visible en interfaz y en el pie de las tandas."],
          ],
          anchos=[5.4, 6.0, 5.4], size=8.5)
    par(doc,
        "El estado del despliegue se declara con precisión: la corrida de evaluación del "
        "capítulo 5 se ejecutó contra la versión en línea, que aún conserva el validador "
        "previo a la corrección; por eso su tasa de rechazo aparece medida en §5.8. La "
        "corrección está implementada y probada en el repositorio, y su redespliegue queda "
        "como paso inmediato de trabajo futuro, con el procedimiento de respaldo y "
        "reconstrucción parcial ya descrito en §4.5.")
    salto(doc)


# ---------------------------------------------------------- capítulo 5 --

def cap5(doc, d):
    t = d.get("turnos") or {}
    r = d.get("ranking") or {}
    e = d.get("encuesta") or {}
    div = t.get("diversidad") or {}
    cum = t.get("cumplimiento") or {}
    voz = t.get("voz") or {}
    inten = t.get("intencion") or {}
    et = t.get("etapas_ms") or {}
    ls = t.get("latencia_servidor_ms") or {}
    lc = t.get("latencia_cliente_ms") or {}
    grad = r.get("agregado_gradado") or {}
    orc = r.get("agregado") or {}
    amp = r.get("agregado_amplio") or {}
    sens = r.get("sensibilidad") or {}
    rk = json.loads((EVA / "ranking.json").read_text(encoding="utf-8")) if (EVA / "ranking.json").exists() else {}
    met = (("hr1", "HR@1"), ("recall10", "Recall@10"), ("rr", "MRR"), ("ndcg10", "NDCG@10"))
    nombres = (("sistema", "EchoPulse (10 tarjetas)"), ("sistema_visible", "EchoPulse (3 visibles)"),
               ("popularidad", "Popularidad global"), ("lexica", "Jaccard léxico"),
               ("aleatorio", "Aleatorio"))

    h1(doc, "CAPÍTULO 5. EVALUACIÓN DEL SISTEMA")
    h2(doc, "5.1 Diseño de la evaluación y protocolo de relevancia")
    par(doc,
        "La unidad de análisis es el turno de conversación y la sesión, no el visitante: el "
        "corpus se generó con un cliente de evaluación contra la demo pública, con sesiones "
        "etiquetadas y semilla fija, y así se declara en todo el capítulo. Cada turno atendido "
        "escribe un evento con el ranking completo de diez posiciones, el perfil prometido, la "
        "cobertura del Módulo 3, la mezcla emergente-reconocido, las latencias por etapa y el "
        "proveedor de la voz; ese registro es el único insumo de las métricas.")
    par(doc,
        "La relevancia se deriva del catálogo, no de etiquetas de usuarios: una pista es "
        "relevante para un turno si pertenece al género pedido y su desvío de ánimo, medido en "
        "cuantiles, no supera el umbral u = 0,25. La variante principal usa ganancia gradada "
        "(1 − desvío), normaliza Recall@10 contra min(|R|, 10) y construye el IDCG con las diez "
        "pistas mejor ajustadas del catálogo. Dos variantes adicionales —coincidencia con el "
        "ideal de diez y conjunto amplio binario— y dos umbrales alternos (0,15 y 0,35) "
        "comprueban que la conclusión no depende de la elección del protocolo. La figura 8 "
        "resume el flujo.")
    fig(doc, 8)
    par(doc,
        "Las tres líneas base se evalúan sobre el mismo corte de diez posiciones: popularidad "
        "global del índice de fama, coincidencia léxica de Jaccard sobre letra y metadatos, y "
        "orden aleatorio con semilla fija. Las listas que entregan menos de diez se rellenan "
        "con vacíos para que la comparación sea justa. El anexo B formaliza las fórmulas.")

    h2(doc, "5.2 Corpus de operación")
    par(doc,
        f"La corrida reunió {mil(t.get('turnos'))} turnos en {mil(t.get('sesiones'))} sesiones, "
        "todos ellos atendidos por el sistema, con un promedio de "
        f"{pc((t.get('turnos_por_sesion') or {}).get('promedio'), 2)} turnos por sesión "
        f"(máximo {mil((t.get('turnos_por_sesion') or {}).get('maximo'))}). La tabla 8 desglosa "
        "tipos de turno y perfiles; las figuras 9 y 10 muestran la profundidad de sesión y el "
        "ritmo de envío.")
    tipos = t.get("tipos_turno") or {}
    etiqueta_tipo = {"musica": "petición de música", "mas_de_lo_mismo": "más de lo mismo",
                     "pregunta": "turno interrogativo", "feedback_positivo": "refuerzo positivo",
                     "solo_genero": "solo género", "solo_animo": "solo ánimo", "ambos": "género y ánimo"}
    tab(doc, 8,
          ["Dimensión", "Desglose medido"],
          [
              ["Turnos y sesiones", f"{mil(t.get('turnos'))} turnos · {mil(t.get('sesiones'))} sesiones"],
              ["Tipos de turno", " · ".join(f"{etiqueta_tipo.get(k, k)}: {mil(v)}" for k, v in tipos.items())],
              ["Turnos por sesión", f"promedio {pc((t.get('turnos_por_sesion') or {}).get('promedio'), 2)} · "
                                   f"máximo {mil((t.get('turnos_por_sesion') or {}).get('maximo'))}"],
              ["Tarjetas registradas", f"{mil(t.get('tarjetas_internas'))} internas · "
                                       f"{mil(t.get('tarjetas_visibles'))} visibles"],
              ["Turnos juzgables", f"{mil(r.get('turnos_juzgados'))} de {mil(t.get('turnos'))} · "
                                   f"{mil((r.get('turnos_procesados') or 0) - (r.get('turnos_juzgados') or 0))} "
                                   "sin perfil de género"],
              ["Perfiles juzgados", " · ".join(f"{etiqueta_tipo.get(k, k)}: {mil(v)}"
                                              for k, v in (rk.get("tipos_perfil") or {}).items())],
          ],
          anchos=[4.6, 12.2], size=8.5)
    par(doc,
        "La clasificación del tipo de turno la hace una heurística léxica del orquestador, sin "
        "modelo de lenguaje: reconoce saludos, refuerzos, peticiones de continuación e "
        "interrogativos antes de caer en la categoría de petición de música. Se declara así "
        "porque es una etiqueta de operación, no un juicio semántico validado.")
    fig(doc, 9)
    fig(doc, 10)

    h2(doc, "5.3 Métricas de orden frente a líneas base")
    par(doc,
        "Con relevancia gradada, el sistema supera a las tres líneas base en las cuatro "
        "métricas. La tabla 9 reporta el valor y su error estándar; la figura 11 las compara. "
        "La lectura correcta es relativa: el conjunto relevante gradado es amplio —toda pista "
        "del género pedido dentro del umbral de ánimo—, de modo que las cifras absolutas "
        "miden cobertura de ese conjunto, no acierto contra una etiqueta única de usuario.")
    filas = []
    for clave, nombre in nombres:
        b = grad.get(clave) or {}
        filas.append([nombre] + [f"{pc(b.get(k), 3)} ± {pc(b.get(k + '_se'), 3)}" for k, _ in met])
    tab(doc, 9, ["Método"] + [n for _, n in met], filas,
        anchos=[4.6, 3.0, 3.0, 3.0, 3.2], size=8.5, der=(1, 2, 3, 4))
    fig(doc, 11)
    par(doc,
        "La variante de tres tarjetas visibles conserva HR@1 y MRR —el primer puesto y el "
        "rango del primer acierto no cambian al cortar— pero reduce Recall@10 y NDCG@10, "
        "porque solo tres de las diez posiciones llegan al oyente. Esa diferencia es la "
        "medida exacta de lo que la interfaz recorta del ranking.")

    h2(doc, "5.4 Robustez del protocolo")
    par(doc,
        "La conclusión se sostiene bajo las tres variantes de relevancia y bajo los dos "
        "umbrales alternos. La tabla 10 contrasta el ideal de diez —donde el conjunto "
        "relevante son exactamente las diez pistas mejor ajustadas y el azar casi no acierta— "
        "con el conjunto amplio binario; la tabla 11 y la figura 12 muestran la sensibilidad "
        "al umbral de ánimo.")
    filas = []
    for clave, nombre in nombres:
        filas.append([nombre,
                      f"{pc((orc.get(clave) or {}).get('hr1'), 3)} / {pc((orc.get(clave) or {}).get('ndcg10'), 3)}",
                      f"{pc((amp.get(clave) or {}).get('hr1'), 3)} / {pc((amp.get(clave) or {}).get('ndcg10'), 3)}"])
    tab(doc, 10, ["Método", "Ideal de diez · HR@1 / NDCG@10", "Amplio binario · HR@1 / NDCG@10"],
        filas, anchos=[5.0, 5.9, 5.9], size=8.5, der=(1, 2))
    filas = []
    for u in ("0.15", "0.25", "0.35"):
        bloque = (sens.get(u) or {}) if u != "0.25" else grad
        b = bloque.get("sistema") or {}
        filas.append([u.replace(".", ",")] + [pc(b.get(k), 3) for k, _ in met])
    tab(doc, 11, ["Umbral u"] + [n for _, n in met], filas,
        anchos=[3.0, 3.4, 3.4, 3.4, 3.6], size=8.5, der=(1, 2, 3, 4))
    fig(doc, 12)
    par(doc,
        f"El tamaño medio del conjunto relevante quedó en {pc(r.get('tamano_relevante_media'), 1)} "
        f"pistas y la fracción de turnos cuya promesa era satisfacible por el catálogo en "
        f"{pc(100 * (r.get('promesas_satisfacibles') or 0))} %: cuando el género pedido no existe "
        "en el catálogo, el turno se omite del juicio en lugar de contarse como fallo.")

    h2(doc, "5.5 Diversidad y descubrimiento")
    par(doc,
        "La tanda interna entregó "
        f"{pc(div.get('emergentes_pct'))} % de artistas emergentes y "
        f"{pc(div.get('reconocidos_pct'))} % de reconocidos, con "
        f"{pc(div.get('artistas_distintos_prom'), 2)} artistas distintos y "
        f"{pc(div.get('generos_distintos_prom'), 2)} géneros distintos por tanda de diez. Ninguna "
        "tarjeta salió sin nombre y ninguna pista se repitió dentro de la sesión. La tabla 12 "
        "y la figura 13 detallan la mezcla; el contraste con las tres tarjetas visibles "
        f"({pc(div.get('emergentes_visibles_pct'))} % emergentes) es el hallazgo central de "
        "diversidad de este trabajo.")
    tab(doc, 12,
          ["Indicador", "Tanda interna (10)", "Tanda visible (3)"],
          [
              ["Artistas emergentes", f"{pc(div.get('emergentes_pct'))} %",
               f"{pc(div.get('emergentes_visibles_pct'))} %"],
              ["Artistas distintos por tanda", pc(div.get("artistas_distintos_prom"), 2),
               pc(div.get("artistas_distintos_visibles_prom"), 2)],
              ["Géneros distintos por tanda", pc(div.get("generos_distintos_prom"), 2), "—"],
              ["Pistas repetidas en la sesión", mil(div.get("repetidas_en_sesion")), "—"],
              ["Tarjetas sin nombre", mil(div.get("sin_nombre")), "—"],
          ],
          anchos=[6.4, 5.2, 5.2], size=8.5, der=(1, 2))
    fig(doc, 13)
    par(doc,
        "Conviene precisar el origen de esa cifra: la mezcla no es un efecto espontáneo del "
        "orden, sino de la cuota de siete huecos emergentes sobre diez descrita en §3.4. El "
        "catálogo tiene señal de fama para la mayoría de sus pistas, de modo que sin cuota la "
        "tanda habría sido mayoritariamente reconocida. La diversidad medida es, por tanto, "
        "diversidad por diseño [15], y su valor está en que se sostiene sin hundir las métricas "
        "de orden de §5.3.")
    par(doc,
        "La lectura es doble y se declara sin adorno: el recomendador descubre —más de la "
        "mitad de lo que ordena es emergente— pero el corte de tres tarjetas visibles "
        "concentra lo reconocido. La hipótesis de diversidad se cumple en el ranking y se "
        "pierde en la interfaz; corregir ese corte es la primera recomendación de trabajo "
        "futuro.")

    h2(doc, "5.6 Coherencia entre lo prometido y lo entregado")
    par(doc,
        f"De los {mil(t.get('turnos'))} turnos, {mil(cum.get('turnos_con_genero'))} pidieron un "
        f"género explícito; en ellos, {pc(cum.get('genero_pct_con_pedido'))} % de las tarjetas "
        f"con género cumplen el pedido. El desvío medio de ánimo quedó en "
        f"{pc(cum.get('desvio_animo_prom'), 3)} cuantiles y el percentil 90 en "
        f"{pc(cum.get('desvio_animo_p90'), 2)}. La tabla 13 y la figura 14 muestran la "
        "distribución completa del desvío.")
    tab(doc, 13,
          ["Indicador de coherencia", "Valor medido"],
          [
              ["Turnos con perfil de género y ánimo", mil(cum.get("turnos_con_perfil"))],
              ["Turnos con perfil heredado del anterior", mil(cum.get("perfil_heredado"))],
              ["Turnos con género pedido", mil(cum.get("turnos_con_genero"))],
              ["Tarjetas con género registrado", mil(cum.get("tarjetas_con_genero"))],
              ["Cumplimiento del género pedido", f"{pc(cum.get('genero_pct_con_pedido'))} %"],
              ["Desvío de ánimo medio · p90",
               f"{pc(cum.get('desvio_animo_prom'), 3)} · {pc(cum.get('desvio_animo_p90'), 2)}"],
          ],
          anchos=[8.4, 8.4], size=8.5, der=(1,))
    fig(doc, 14)

    h2(doc, "5.7 Latencia del turno")
    par(doc,
        f"La latencia mediana declarada por el servidor fue de {seg(ls.get('p50'))} s y el "
        f"percentil 90 de {seg(ls.get('p90'))} s; el cliente midió {seg(lc.get('p50'))} s y "
        f"{seg(lc.get('p90'))} s, una diferencia pequeña y constante que corresponde al túnel y "
        "a la red. El desglose por etapa muestra que traducir, recuperar y reordenar suman "
        "menos de tres décimas de segundo: el costo está en la generación con el modelo de "
        "lenguaje sobre dos núcleos. La tabla 14 y las figuras 15 y 16 lo documentan.")
    filas = []
    for clave, nombre in (("translation", "Traducción e intención"), ("retrieval", "Recuperación M2"),
                          ("reranking", "Reordenamiento M3"), ("generation", "Generación con Qwen"),
                          ("total", "Turno completo")):
        b = et.get(clave) or {}
        filas.append([nombre, pc(b.get("promedio"), 1), pc(b.get("p90"), 1)])
    tab(doc, 14, ["Etapa", "Media (ms)", "p90 (ms)"], filas,
        anchos=[7.0, 4.9, 4.9], size=8.5, der=(1, 2))
    fig(doc, 15)
    fig(doc, 16)
    par(doc,
        "Con un único slot de generación, dos visitantes simultáneos se atienden de uno en "
        "uno: la cola existe por diseño y protege la máquina. La corrida envió los turnos "
        "espaciados, de modo que lo medido es el costo base; una prueba de concurrencia real "
        "queda declarada como trabajo futuro.")

    h2(doc, "5.8 Voz conversacional e intención")
    par(doc,
        f"El modelo de lenguaje escribió {mil(voz.get('llm'))} respuestas y el motor "
        f"determinista {mil(voz.get('determinista'))}, una tasa de rechazo del "
        f"{pc(voz.get('tasa_rechazo_pct'))} %. Esa tasa corresponde al validador previo a la "
        "corrección descrita en §4.6, que aún no se había redesplegado cuando se generó el "
        "corpus; se reporta como medición del artefacto en línea, no como defecto del "
        "repositorio actual. La intención la aportó la heurística determinista en "
        f"{mil((inten.get('por_fuente') or {}).get('heuristica'))} turnos y el modelo en "
        f"{mil((inten.get('por_fuente') or {}).get('custom'))}; la cobertura media del Módulo 3 "
        f"sobre la tanda fue de {pc(inten.get('cobertura_m3_prom_pct'))} % y la cobertura de "
        f"metadatos de {pc(inten.get('metadata_prom_pct'))} %.")
    tab(doc, 15,
          ["Indicador", "Valor medido", "Lectura"],
          [
              ["Respuestas del modelo de lenguaje", mil(voz.get("llm")),
               "Voz generada y validada."],
              ["Respuestas deterministas", mil(voz.get("determinista")),
               f"{pc(voz.get('tasa_rechazo_pct'))} % de rechazo del validador en línea."],
              ["Intención por heurística · por LLM",
               f"{mil((inten.get('por_fuente') or {}).get('heuristica'))} · "
               f"{mil((inten.get('por_fuente') or {}).get('custom'))}",
               "El perfil nunca queda vacío: la heurística respalda al modelo."],
              ["Cobertura media del Módulo 3", f"{pc(inten.get('cobertura_m3_prom_pct'))} %",
               "Fracción de la tanda con clase conocida; causa visible del reordenamiento."],
              ["Cobertura de metadatos", f"{pc(inten.get('metadata_prom_pct'))} %",
               "Toda tarjeta lleva nombre y artista reales."],
          ],
          anchos=[5.4, 4.0, 7.4], size=8.5, der=(1,))

    h2(doc, "5.9 Instrumento cualitativo: descripción completa")
    par(doc,
        "El instrumento es un formulario externo de veinte afirmaciones en escala de cinco "
        "puntos más un comentario libre, enlazado desde la demo. Su exportación contiene "
        f"{mil(e.get('filas'))} filas: {mil(e.get('validas'))} con los veinte ítems respondidos y "
        f"{mil(e.get('sin_responder'))} envíos sin ninguna respuesta, recogidos entre "
        f"{str(e.get('hora_primera'))[:16].replace('T', ' ')} y "
        f"{str(e.get('hora_ultima'))[:16].replace('T', ' ')}. Se reporta completo y de forma "
        "descriptiva, tal como fue registrado.")
    tab(doc, 16,
          ["Bloque temático", "Ítems", "Media", "DT", "% de respuestas 5"],
          [[b["nombre"], ", ".join(str(i) for i in b["items"]), nm(b["media"], 2),
            nm(b["sd"], 2), f"{nm(b['p5'])} %"] for b in e.get("bloques") or []],
          anchos=[5.6, 2.6, 2.2, 2.2, 4.2], size=8.5, der=(2, 3, 4))
    fig(doc, 17)
    fig(doc, 18)
    escala = e.get("escala") or {}
    tab(doc, 17,
          ["Resumen del instrumento", "Valor registrado"],
          [
              ["Respuestas completas · envíos vacíos",
               f"{mil(e.get('validas'))} · {mil(e.get('sin_responder'))}"],
              ["Media global de los veinte ítems", nm(e.get("media_global"), 2)],
              ["Distribución de la escala",
               " · ".join(f"{k}: {mil(v)}" for k, v in sorted(escala.items()))],
              ["Alfa de Cronbach (20 ítems)", nm(e.get("alfa_cronbach"), 3)],
              ["Correlación inter-ítem media", nm(e.get("corr_interitem"), 3)],
              ["Comentarios · textos distintos",
               f"{mil(len(e.get('comentarios') or []))} · {mil(e.get('comentarios_distintos'))}"],
              ["Comentario más repetido",
               f"«{(e.get('comentario_repetido') or [['—', 0]])[0][0]}» × "
               f"{mil((e.get('comentario_repetido') or [['—', 0]])[0][1])}"],
          ],
          anchos=[7.0, 9.8], size=8.5)
    fig(doc, 19)
    par(doc,
        "La consistencia interna observada es baja: alfa de "
        f"{nm(e.get('alfa_cronbach'), 3)} y correlación inter-ítem media de "
        f"{nm(e.get('corr_interitem'), 3)}, con respuestas concentradas en los valores 3, 4 y 5 "
        "de la escala. En un cuestionario de percepción contestado por personas se espera "
        "correlación inter-ítem sustancialmente mayor; por eso la media global se presenta "
        "como descripción de lo registrado y no como medida de un constructo de satisfacción, "
        "y no se usa para afirmar nada sobre usuarios. El instrumento queda publicado y "
        "enlazado; su recolección con participantes reclutados por un canal verificable es "
        "trabajo futuro declarado.")

    h2(doc, "5.10 Discusión integrada y limitaciones")
    par(doc,
        "Los resultados se leen juntos. El sistema ordena por afinidad de contenido y supera a "
        "popularidad, léxico y azar en las cuatro métricas de orden, bajo tres variantes de "
        "relevancia y dos umbrales alternos: la mitad de precisión de la hipótesis se sostiene. "
        "La tanda interna es mayoritariamente emergente y diversa: la mitad de descubrimiento "
        "se sostiene en el ranking. El punto donde la hipótesis se tensiona es el corte de "
        "interfaz, que concentra lo reconocido en las tres tarjetas visibles; y el punto donde "
        "el sistema paga su apuesta por CPU barata es la latencia de generación, con mediana "
        "cercana a ocho segundos.")
    par(doc,
        "Las limitaciones se declaran sin atenuarlas. El corpus es de turnos generados contra "
        "la demo, no de visitantes espontáneos: mide el sistema, no la percepción de una "
        "población. La relevancia es derivada del catálogo, no etiquetada por oyentes: es "
        "auditable y reproducible, pero no sustituye un estudio con usuarios. El instrumento "
        "cualitativo tiene consistencia interna baja y se reporta solo como descripción. La "
        "concurrencia real no se midió. Y la corrección del validador, probada en el "
        "repositorio, no estaba en línea durante la corrida: su efecto se medirá en la "
        "siguiente corrida, con el mismo protocolo.")
    salto(doc)


# ---------------------------------------------------------- capítulo 6 --

def cap6(doc, d):
    t = d.get("turnos") or {}
    r = d.get("ranking") or {}
    g = (r.get("agregado_gradado") or {}).get("sistema") or {}
    div = t.get("diversidad") or {}
    h1(doc, "CAPÍTULO 6. CONCLUSIONES Y TRABAJO FUTURO")
    h2(doc, "6.1 Conclusiones")
    par(doc,
        "Objetivo específico 1, consolidar datos musicales en una arquitectura local: "
        f"cumplido. La tabla maestra de {mil((r.get('insumos') or {}).get('pistas'))} pistas y "
        "cuarenta y ocho columnas, el índice de fama de 545.983 entradas y los seis rasgos de "
        "ánimo en cuantiles quedaron versionados y son la única fuente de verdad del sistema; "
        "ninguna consulta en línea depende de una API externa.")
    par(doc,
        "Objetivo específico 2, entrenar un modelo Transformer con fusión multimodal: "
        "cumplido. El Transformer de contenido convergió de MSE 0,0289 a 0,0002 en quince "
        "épocas con atención cruzada entre letra y rasgos técnicos, y el Transformer de "
        "intención se entrenó y validó sobre 38.343 clases con su aporte medido en la mezcla "
        "final.")
    par(doc,
        "Objetivo específico 3, comparar precisión, diversidad, intención y latencia frente a "
        f"líneas base: cumplido sobre {mil(t.get('turnos'))} turnos. Con relevancia gradada el "
        f"sistema alcanzó HR@1 {pc(g.get('hr1'), 3)}, Recall@10 {pc(g.get('recall10'), 3)}, MRR "
        f"{pc(g.get('rr'), 3)} y NDCG@10 {pc(g.get('ndcg10'), 3)}, por encima de las tres líneas "
        f"base; la tanda interna entregó {pc(div.get('emergentes_pct'))} % de emergentes con "
        f"{pc(div.get('artistas_distintos_prom'), 2)} artistas distintos por tanda.")
    par(doc,
        "Sobre la pregunta de investigación, la respuesta es afirmativa con un matiz "
        "delimitado: un recomendador multimodal local puede mejorar la diversidad y el "
        "descubrimiento sin sacrificar precisión en el ranking que produce; el descubrimiento "
        "se pierde en el corte de la interfaz, que es un problema de política de presentación "
        "y no del modelo. La hipótesis queda sostenida en el nivel donde el sistema decide, y "
        "el trabajo futuro apunta al nivel donde el oyente ve.")
    tab(doc, 18,
          ["Objetivo", "Resultado esperado", "Resultado alcanzado medido"],
          [
              ["O.E.1 · Datos locales", "Catálogo consolidado y auditable.",
               "5.710 pistas × 48 columnas; índice de fama de 545.983 entradas."],
              ["O.E.2 · Transformer multimodal", "Modelo entrenado con fusión real.",
               "MSE 0,0289 → 0,0002; M3 con 38.343 clases y validación aislada."],
              ["O.E.3 · Comparación", "Métricas de orden y diversidad sobre líneas base.",
               f"HR@1 {pc(g.get('hr1'), 3)} · Recall@10 {pc(g.get('recall10'), 3)} · MRR "
               f"{pc(g.get('rr'), 3)} · NDCG@10 {pc(g.get('ndcg10'), 3)}; "
               f"{pc(div.get('emergentes_pct'))} % emergentes internos."],
          ],
          anchos=[4.0, 5.4, 7.4], size=8.5)

    h2(doc, "6.2 Trabajo futuro")
    viñetas(doc, [
        ("Redesplegar el validador corregido y volver a medir. ",
         "Con el procedimiento de respaldo y reconstrucción parcial de §4.5, y una corrida "
         "gemela que permita comparar la tasa de rechazo antes y después."),
        ("Corregir el corte visible. ",
         "Subir el número de destacadas o intercalar un emergente por tanda, y volver a medir "
         "la mezcla visible con el mismo protocolo de §5.5."),
        ("Avisar cuando el catálogo no alcanza. ",
         f"En {mil((r.get('saltos') or {}).get('catalogo_no_alcanza'))} turnos el género pedido no "
         "tenía material suficiente y el juicio los omitió; el agente debería decírselo al oyente "
         "en lugar de entregar lo más cercano en silencio."),
        ("Recolectar etiquetas de oyentes. ",
         "El gesto de gusto por tarjeta ya existe en la API; con veinte a treinta participantes "
         "reales las métricas de orden pueden contrastarse contra relevancia humana."),
        ("Rehacer la recolección cualitativa. ",
         "Participantes reclutados por un canal verificable, en un rango de fechas amplio y "
         "con consentimiento, para que la consistencia interna sea interpretable."),
        ("Prueba de concurrencia real. ",
         "Varios visitantes simultáneos contra el slot único de generación, para cuantificar "
         "la espera que hoy solo se conoce por diseño."),
        ("Registro de software y artículo. ",
         "Formalizar el registro del sistema y enviar el artículo con el protocolo y las "
         "cifras de este documento."),
    ])
    salto(doc)


# ------------------------------------------------------- referencias/anexos --

def referencias(doc):
    h1(doc, "REFERENCIAS")
    for i, ref in enumerate(bib.REFERENCIAS, 1):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.9)
        p.paragraph_format.first_line_indent = Cm(-0.9)
        p.paragraph_format.space_after = Pt(4)
        r = p.add_run(f"[{i}] ")
        r.bold = True
        p.add_run(ref)
    salto(doc)


def anexos(doc, d):
    h1(doc, "ANEXOS")
    h2(doc, "Anexo A. Depuración de la bibliografía")
    par(doc,
        "Cada referencia se verificó contra la fuente original. Las citas del anteproyecto "
        "que no pudieron localizarse se retiraron o se corrigieron; el registro completo "
        "queda aquí para que la corrección sea auditable.")
    tabla(doc, ["Cita del anteproyecto", "Hallazgo de la verificación", "Resolución"],
          [list(c) for c in bib.CORRECCIONES],
          anchos=[5.2, 6.2, 5.4], size=8,
          caption="Tabla A.1. Depuración de citas no verificables.")
    h2(doc, "Anexo B. Fórmulas del protocolo de relevancia")
    par(doc,
        "Para un turno con género pedido g y ánimo objetivo a, el conjunto relevante es "
        "R = {pista del género g con desvío de ánimo d(p) ≤ u}, con u = 0,25 y desvío medido "
        "en cuantiles del catálogo. La ganancia gradada es rel(p) = 1 − d(p). Con la lista "
        "ordenada L de diez posiciones:")
    for linea in (
        "HR@k = 1 si alguna de las primeras k posiciones de L pertenece a R; 0 en otro caso.",
        "Recall@10 = |L ∩ R| / min(|R|, 10).",
        "MRR = 1 / rango de la primera posición de L que pertenece a R; 0 si no hay.",
        "DCG@10 = Σ rel(L_i) / log2(i + 1) para i = 1..10; NDCG@10 = DCG@10 / IDCG@10.",
        "IDCG@10 = DCG de las diez pistas de R con menor desvío, ordenadas por ganancia.",
        "Variante ideal de diez: R = las 10 de menor desvío, ganancia binaria.",
        "Variante amplia: R = toda pista que cumple, ganancia binaria, Recall sobre |R|.",
        "Error estándar de cada métrica: desviación típica entre turnos / raíz del número de turnos.",
    ):
        p = doc.add_paragraph()
        r = p.add_run(linea)
        r.font.name = "Consolas"
        r.font.size = Pt(8.5)
        p.paragraph_format.space_after = Pt(2)
    h2(doc, "Anexo C. Inventario de artefactos y versiones")
    tabla(doc, ["Artefacto", "Ruta", "Contenido"],
          [
              ["Monografía", "docs/EchoPulse_AI_monografia.docx", "Este documento."],
              ["Informe Anexo 3", "docs/EchoPulse_AI_informe_final.docx",
               "Informe final con el formato institucional del Anexo 3."],
              ["Documento de arquitectura", "docs/EchoPulse_AI_arquitectura_detalle.html",
               "Detalle de módulos, datos y decisiones de diseño."],
              ["Presentación de defensa", "docs/EchoPulse_AI_presentacion_tesis.pptx",
               "Láminas con el diagrama de arquitectura en vectores."],
              ["Composición de servicios", "deploy/azure-compose.yaml",
               "app, qwen y los dos túneles, con comentarios de cada decisión."],
              ["Cliente de evaluación", "echopulse_llm_orquestator/scripts/cliente_evaluacion.py",
               "Genera turnos contra la demo y conserva el ranking completo."],
              ["Evaluador de ranking", "echopulse_llm_orquestator/scripts/evaluar_ranking.py",
               "Métricas de orden, variantes, sensibilidad y líneas base."],
              ["Figuras", "docs/monografia_assets y docs/informe_final_assets",
               "Diagramas de arquitectura y figuras de resultados, por script."],
              ["Corpus y cifras", "build/eva/", "Turnos JSONL, ranking.json y datos_informe.json."],
          ],
          anchos=[4.0, 6.6, 6.2], size=8,
          caption="Tabla C.1. Artefactos del proyecto y su ubicación.")
    h2(doc, "Anexo D. Reproducción de la medición")
    par(doc, "Desde la carpeta echopulse_llm_orquestator, con el catálogo local en la raíz:")
    for linea in (
        "python scripts/cliente_evaluacion.py --total 330 --rpm 9",
        "python scripts/evaluar_ranking.py --logs \"../build/eva/turnos_*.jsonl\" \\",
        "    --catalogo \"../tabla_maestra/train/*.parquet\" \\",
        "    --fama models/fame_index.parquet --salida ../build/eva/ranking.json",
        "python scripts/graficas_final.py",
        "python scripts/figuras_arquitectura.py",
        "python scripts/monografia.py",
        "python scripts/informe_final.py",
    ):
        p = doc.add_paragraph()
        r = p.add_run(linea)
        r.font.name = "Consolas"
        r.font.size = Pt(8.5)
        p.paragraph_format.space_after = Pt(0)
    par(doc, "")
    par(doc, "La corrida respeta el limitador de la demo: ante un 429 espera y reintenta, y "
             "nunca falsifica la cabecera de dirección de origen. Un archivo STOP en la "
             "carpeta de salida aborta la corrida de forma limpia.", size=9, color=GRIS,
        italic=True)


def main() -> int:
    ruta = EVA / "datos_informe.json"
    if not ruta.exists():
        print("falta build/eva/datos_informe.json; ejecute antes graficas_final.py")
        return 1
    d = json.loads(ruta.read_text(encoding="utf-8"))
    doc = Document()
    preparar(doc)
    actualizar_campos(doc)
    portadas(doc)
    dedicatoria_agradecimientos(doc)
    indices(doc)
    resumen(doc, d)
    introduccion(doc, d)
    cap1(doc, d)
    cap2(doc, d)
    cap3(doc, d)
    cap4(doc, d)
    cap5(doc, d)
    cap6(doc, d)
    referencias(doc)
    anexos(doc, d)
    destino = RAIZ / "docs" / "EchoPulse_AI_monografia.docx"
    doc.save(destino)
    palabras = sum(len(p.text.split()) for p in doc.paragraphs)
    print(f"escrito {destino}")
    print(f"párrafos {len(doc.paragraphs)} · tablas {len(doc.tables)} · "
          f"figuras {len(FIGS)} · palabras ~{mil(palabras)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())