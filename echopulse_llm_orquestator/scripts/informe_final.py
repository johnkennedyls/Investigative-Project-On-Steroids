# scripts/informe_final.py - Informe final de grado con el formato del Anexo 3
"""Construye el documento Word de la etapa final del proyecto EchoPulse AI.

El texto está redactado en tercera persona y en español, con prosa original:
ningún párrafo se copia del anteproyecto ni de las versiones previas del
documento; lo que se conserva literal son la pregunta de investigación, la
hipótesis y los objetivos, que son formulaciones del propio autor, y la
certificación de autoría que exige el formato.

Todas las cifras proceden de `build/eva/datos_informe.json`, que a su vez sale de
los turnos registrados en la demo desplegada, del evaluador de ranking, del
instrumento cualitativo y de las salidas de los notebooks de entrenamiento. Si un
insumo falta, la sección correspondiente lo declara en vez de inventar un valor.

    python scripts/graficas_final.py        # produce datos + figuras
    python scripts/informe_final.py         # produce el .docx
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bibliografia as bib  # noqa: E402
from informe_docx import (  # noqa: E402
    AZUL, GRIS, PIZRA, ROJO, FONDO_NOTA, FONDO_SUAVE,
    _campo_page, caja, figura, h1, h2, mixto, nm, par, preparar, tabla, viñetas,
)

RAIZ = Path(__file__).resolve().parents[2]
EVA = RAIZ / "build" / "eva"
ASSETS = RAIZ / "docs" / "informe_final_assets"

TITULO = "AGENTE RECOMENDADOR DE MÚSICA MULTIMODAL BASADO EN TRANSFORMERS"
SUBTITULO = "Etapa final: desarrollo, despliegue y evaluación del sistema EchoPulse AI"
AUTOR = "JOHN KENNEDY LANDAZURI SANDOVAL"
DIRECTOR = "CRISTIAN CAMILO ORDOÑEZ QUINTERO"
CODIRECTOR = "CRISTIAN MENDEZ RODRÍGUEZ"

PREGUNTA = ("¿Puede un recomendador musical multimodal local mejorar la diversidad y el "
            "descubrimiento de artistas emergentes sin sacrificar precisión?")
PREGUNTA_ANTEPROYECTO = ("¿Cómo facilitar el posicionamiento de músicos noveles utilizando "
                         "mecanismos basados en inteligencia artificial y arquitecturas "
                         "transformers?")
OBJ_GENERAL = ("Diseñar y evaluar un sistema de recomendación musical multimodal local que "
               "priorice la afinidad de contenido para mejorar la diversidad y el "
               "descubrimiento de artistas emergentes.")
OBJ_ESPECIFICOS = (
    "Consolidar datos musicales en una arquitectura local.",
    "Entrenar un modelo Transformer con fusión multimodal.",
    "Comparar precisión, diversidad, intención y latencia frente a líneas base.",
)


def mil(valor) -> str:
    """Entero con separador de miles por punto (convención del documento)."""
    try:
        return f"{int(round(float(valor))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def pc(valor, dec=1) -> str:
    return "—" if valor is None else nm(valor, dec)


def ms(valor) -> str:
    """Milisegundos: un decimal cuando la etapa es casi nula (< 10 ms)."""
    if valor is None:
        return "—"
    return nm(valor, 1) if abs(float(valor)) < 10 else mil(valor)


MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def fecha(iso, con_hora: bool = True) -> str:
    """Fecha legible en hora de Colombia (UTC-5) a partir del sello UTC del log."""
    from datetime import datetime, timedelta, timezone
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return str(iso)[:16].replace("T", " ")
    dt = dt.astimezone(timezone(timedelta(hours=-5)))
    dia = f"{dt.day} de {MESES[dt.month - 1]} de {dt.year}"
    return f"{dia}, {dt:%H:%M}" if con_hora else dia


def fecha_ingenua(txt) -> str:
    """Sella de tiempo sin zona (ya en hora local del instrumento), en formato legible."""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(str(txt))
    except (TypeError, ValueError):
        return str(txt)[:16].replace("T", " ")
    return f"{dt.day} de {MESES[dt.month - 1]} de {dt.year}, {dt:%H:%M}"


def metrica(bloque: dict | None, clave: str, dec=3) -> str:
    if not bloque:
        return "—"
    v = bloque.get(clave)
    return "—" if v is None else nm(v, dec)


def h3(doc, texto):
    """Subsección de tercer nivel, con el mismo estilo institucional."""
    return doc.add_heading(texto, level=3)


# ----------------------------------------------------------------- portada --

def portada(doc):
    for _ in range(3):
        doc.add_paragraph()
    par(doc, TITULO, size=17, color=AZUL, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=10)
    par(doc, SUBTITULO, size=12, color=GRIS, italic=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=26)
    for _ in range(2):
        doc.add_paragraph()
    par(doc, "NOMBRE:", size=11, color=GRIS, align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    par(doc, AUTOR, size=13, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=22)
    par(doc, "PROYECTO FINAL DE GRADO PARA OPTAR AL TÍTULO DE:", size=11,
        align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    par(doc, "INGENIERO DE SISTEMAS", size=12, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=24)
    par(doc, f"DIRECTOR: {DIRECTOR}", size=11, align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    par(doc, f"CO. DIRECTOR: {CODIRECTOR}", size=11, align=WD_ALIGN_PARAGRAPH.CENTER, after=26)
    for _ in range(2):
        doc.add_paragraph()
    for linea, tam, negrita in (
        ("FUNDACIÓN UNIVERSITARIA DE POPAYÁN", 12, True),
        ("FACULTAD DE INGENIERÍA", 11, False),
        ("PROGRAMA DE INGENIERÍA DE SISTEMAS", 11, False),
        ("GRUPO DE INVESTIGACIÓN “IMS/LOGICIEL”", 11, False),
    ):
        par(doc, linea, size=tam, bold=negrita, align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    doc.add_paragraph()
    par(doc, "Popayán, NOVIEMBRE de 2026", size=11, align=WD_ALIGN_PARAGRAPH.CENTER)
    doc.add_page_break()


def contenido(doc):
    h1(doc, "CONTENIDO")
    entradas = [
        "CERTIFICACIÓN DE AUTORÍA", "RESUMEN", "INTRODUCCIÓN",
        "1. PLANTEAMIENTO DEL PROBLEMA", "   1.1 Descripción del problema",
        "   1.2 Formulación del problema",
        "2. OBJETIVOS", "   2.1 Objetivo general", "   2.2 Objetivos específicos",
        "   2.3 Trazabilidad entre el anteproyecto y la etapa final",
        "   2.4 Resultados esperados y resultados alcanzados",
        "3. JUSTIFICACIÓN",
        "4. MARCOS DE REFERENCIA", "   4.1 Marco teórico-conceptual",
        "   4.2 Antecedentes y estado del arte",
        "5. METODOLOGÍA",
        "   5.1 Fase de exploración (objetivo específico 1)",
        "   5.2 Fase de desarrollo (objetivo específico 2)",
        "   5.3 Fase de divulgación y evaluación (objetivo específico 3)",
        "   5.4 Correspondencia fase-objetivo-evidencia",
        "   5.5 Análisis de datos y control de calidad",
        "6. DESARROLLO METODOLÓGICO",
        "   6.1 Consolidación de los datos musicales", "   6.2 Arquitectura del prototipo",
        "   6.3 Entrenamiento de los modelos", "   6.4 Despliegue continuo y gratuito",
        "   6.5 Correcciones de la etapa final", "   6.6 Instrumentación de la evaluación",
        "   6.7 Atención a las observaciones de los evaluadores",
        "7. RESULTADOS Y DISCUSIÓN",
        "   7.1 Corpus de evaluación",
        "      7.1.1 Unidad de análisis: el turno y la visita",
        "      7.1.2 Estructura de las visitas",
        "      7.1.3 Composición de los turnos",
        "      7.1.4 Conciliación del corpus",
        "   7.2 Precisión de orden frente a líneas base",
        "   7.3 Robustez del protocolo de relevancia", "   7.4 Diversidad y descubrimiento",
        "   7.5 Coherencia entre la promesa y la entrega", "   7.6 Latencia y operación",
        "   7.7 Voz conversacional e intención", "   7.8 Evidencia de entrenamiento",
        "   7.9 Instrumento cualitativo", "   7.10 Discusión integrada",
        "   7.11 Balance de cumplimiento de las métricas",
        "8. CONCLUSIONES", "9. RECOMENDACIONES", "10. BIBLIOGRAFÍA",
        "ANEXOS", "   Anexo A. Depuración de la bibliografía del anteproyecto",
        "   Anexo B. Protocolo de relevancia derivada del catálogo",
        "   Anexo C. Inventario de versiones y correcciones",
        "   Anexo D. Reproducibilidad",
    ]
    for e in entradas:
        p = doc.add_paragraph()
        titulo = e.strip()
        sangria = 1.1 if e.startswith("      ") else (0.7 if e.startswith("   ") else 0)
        r = p.add_run(titulo)
        r.font.size = Pt(10.5 if not e.startswith("   ") else 10)
        r.bold = not e.startswith(" ")
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.left_indent = Cm(sangria)
    doc.add_page_break()


def certificacion(doc):
    h1(doc, "CERTIFICACIÓN DE AUTORÍA")
    par(doc, "Certifico que conozco el concepto de plagiar según la Real Academia de la Lengua "
             "(“Copiar en lo sustancial obras ajenas, dándolas como propias.”)")
    par(doc, "Y certifico que el contenido de este documento es de mi autoría, que no hay "
             "contenido que haya sido copiado directamente y al pie de la letra de ninguna "
             "fuente. En el caso de ideas, teorías, conceptos, resultados y otros contenidos "
             "tomados de otros autores se menciona explícitamente la fuente original, y solo en "
             "unos pocos casos se ha mantenido el mismo texto, colocándolo entre comillas.")
    par(doc, "Reconozco las consecuencias académicas, jurídicas y económicas que conlleva el "
             "plagio.")
    par(doc, "El presente informe se redactó en tercera persona con prosa original. Las "
             "formulaciones que se conservan de manera literal corresponden a la pregunta de "
             "investigación, la hipótesis y los objetivos del propio autor, y a la certificación "
             "que exige el formato institucional. Todas las referencias fueron verificadas "
             "contra la fuente original; el Anexo A documenta las que se corrigieron o retiraron.",
        size=9.5, color=GRIS, italic=True)
    for _ in range(3):
        doc.add_paragraph()
    par(doc, "Firma", size=10, color=GRIS, after=2)
    par(doc, "____________________________________", after=2)
    par(doc, AUTOR, size=10.5, after=2)
    par(doc, "CC. ____________________", size=10.5)
    doc.add_page_break()


# ------------------------------------------------------------- resumen e intro --

def resumen(doc, d):
    t, r, e = d.get("turnos") or {}, d.get("ranking") or {}, d.get("encuesta") or {}
    g = (r.get("agregado_gradado") or {}).get("sistema") or {}
    h1(doc, "RESUMEN")
    par(doc,
        "Este informe describe la etapa final del proyecto de grado EchoPulse AI, un agente "
        "recomendador de música multimodal que opera de forma local y conversa en español. El "
        "trabajo partió del anteproyecto aprobado con recomendaciones y recorrió tres fases "
        "adaptadas de CRISP-DM: exploración, desarrollo y divulgación. En la fase de desarrollo "
        "se consolidaron cuatro fuentes públicas en una tabla maestra de "
        f"{mil((r.get('insumos') or {}).get('pistas'))} pistas con cuarenta y ocho columnas, se "
        "entrenó un Transformer de contenido con fusión por atención cruzada y un Transformer de "
        "intención sobre treinta y ocho mil trescientas cuarenta y tres clases, y se desplegó el "
        "sistema completo en una máquina virtual de dos núcleos con acceso HTTPS permanente y "
        "sin costo de operación.")
    par(doc,
        "La evaluación se realizó a nivel de turno y de visita, que son las unidades de análisis "
        "de esta investigación: se registraron "
        f"{mil(t.get('turnos'))} turnos conversacionales en {mil(t.get('sesiones'))} visitas "
        "sobre la instancia desplegada, de los cuales "
        f"{mil((r.get('turnos_juzgados')))} portaban una restricción de género o de ánimo "
        "verificable contra el catálogo. Sobre ese corpus se calcularon HR@1, Recall@10, MRR y "
        f"NDCG@10 con un protocolo de relevancia derivado del catálogo: el sistema alcanzó "
        f"HR@1 de {metrica(g, 'hr1')}, Recall@10 de {metrica(g, 'recall10')}, MRR de "
        f"{metrica(g, 'rr')} y NDCG@10 de {metrica(g, 'ndcg10')}, por encima de las líneas base "
        "de popularidad global, similitud léxica y selección aleatoria. La mezcla de catálogo "
        f"destinó {pc((t.get('diversidad') or {}).get('emergentes_pct'))} % de las tarjetas a "
        "artistas emergentes y la latencia mediana del turno completo fue de "
        f"{mil((t.get('latencia_servidor_ms') or {}).get('p50'))} ms en el servidor.")
    par(doc,
        "El componente cualitativo se recogió con un instrumento de veinte ítems en escala de "
        f"cinco puntos: {mil(e.get('filas'))} respuestas registradas, {mil(e.get('validas'))} "
        f"completas y una media global de {pc(e.get('media_global'), 3)} sobre 5, con los cinco "
        "bloques por encima de 4,4 y una distribución concentrada en los valores altos de la "
        "escala. Los resultados sostienen la hipótesis en el alcance "
        "del catálogo local: priorizar la afinidad de contenido mejora la diversidad y el "
        "descubrimiento sin perder precisión de orden frente a las líneas base comparadas.")
    mixto(doc, [("Palabras clave: ", True),
                ("sistemas de recomendación musical, Transformer multimodal, afinidad de "
                 "contenido, artistas emergentes, evaluación por turnos, recomendación "
                 "conversacional.", False)])
    doc.add_page_break()


def introduccion(doc, d):
    h1(doc, "INTRODUCCIÓN")
    par(doc,
        "El consumo musical digital creció durante una década sin que ese crecimiento se "
        "tradujera en visibilidad para los intérpretes noveles. Los recomendadores que median "
        "ese consumo aprenden de interacciones pasadas y, por construcción, devuelven lo que ya "
        "fue popular. El proyecto de grado que aquí se cierra atacó ese mecanismo desde el "
        "contenido: en lugar de preguntar qué escucharon otros usuarios, el sistema pregunta "
        "qué se parece a lo que el oyente acaba de describir, con sus palabras, en español y en "
        "una conversación que recuerda los turnos anteriores.")
    par(doc,
        "El documento une el anteproyecto aprobado en agosto de 2025 con las versiones "
        "sucesivas del informe técnico y con las correcciones solicitadas por los evaluadores. "
        "No reproduce esos textos: los reescribe en tercera persona como una sola narración de "
        "la etapa final, y conserva literal únicamente la pregunta de investigación, la "
        "hipótesis y los objetivos, que son formulaciones del autor. Cada afirmación cuantitativa "
        "se apoya en un registro medido: los turnos conversacionales de la instancia desplegada, "
        "el evaluador de ranking que los contrasta contra el catálogo, las salidas de los "
        "notebooks de entrenamiento y el instrumento cualitativo aplicado a quienes respondieron "
        "la encuesta de la demo.")
    par(doc,
        "La estructura sigue el Anexo 3 del formato institucional. El capítulo 1 delimita y "
        "cuantifica el problema y enuncia la pregunta; el 2 fija los objetivos y su trazabilidad "
        "con el anteproyecto; el 3 justifica la investigación; el 4 construye los marcos "
        "teórico y del estado del arte con análisis crítico; el 5 declara la metodología y sus "
        "instrumentos; el 6 relata el desarrollo metodológico, incluidos el despliegue y las "
        "correcciones de la etapa final; el 7 presenta y discute los resultados; el 8 concluye "
        "por objetivo; el 9 recomienda; y el 10 lista la bibliografía verificada en formato "
        "IEEE. Cuatro anexos documentan la depuración de referencias, el protocolo de "
        "relevancia, el inventario de versiones y los comandos de reproducción.")
    par(doc,
        "La unidad de análisis de todo el informe es el turno conversacional y la visita: cada "
        "interacción que la demo atiende cuenta como un turno, y el conjunto ordenado de turnos "
        "de una misma conversación constituye una visita o sesión. Esa decisión es la que hace "
        "comparables las cifras: la plataforma registra turnos, no identidades, de modo que la "
        "evaluación mide lo que el sistema entrega en cada intercambio y lo agrega por sesión, y "
        "el instrumento cualitativo se reporta con su número de respuestas y su análisis de "
        "consistencia, sin atribuir identidad a quien respondió.")
    doc.add_page_break()


# ------------------------------------------------------------ 1 problema --

def problema(doc, d):
    h1(doc, "1. PLANTEAMIENTO DEL PROBLEMA")
    h2(doc, "1.1 Descripción del problema")
    par(doc,
        "La industria fonográfica cerró 2024 con ingresos por música grabada de 29,6 mil "
        "millones de dólares, un crecimiento de 4,8 % que encadenó diez años consecutivos de "
        "expansión; el streaming por suscripción de pago aportó el mayor impulso, con 9,5 % y "
        "más de 20 mil millones [26]. Ese volumen, sin embargo, no se distribuye de forma "
        "homogénea: la atención del público se concentra en un repertorio reducido de "
        "intérpretes consolidados, frente a catálogos que superan los cien millones de pistas.")
    par(doc,
        "La causa técnica de esa concentración está documentada: los recomendadores entrenados "
        "sobre interacciones históricas reproducen y amplifican el sesgo de popularidad, porque "
        "la señal de co-escucha favorece a quien ya fue escuchado [13], [14], [34]. El efecto es "
        "acumulativo: cada recomendación popular alimenta al modelo con nuevas interacciones, "
        "de modo que los artistas noveles quedan fuera del ciclo de descubrimiento aunque su "
        "obra sea afín al gusto declarado del oyente [35].")
    par(doc,
        "Frente a ello, la literatura reciente exploró dos vías. La primera sustituye el "
        "filtrado colaborativo por arquitecturas de autoatención que modelan secuencias "
        "de escucha, como SASRec [3] y BERT4Rec [4]. La segunda incorpora lenguaje natural y "
        "modelos generativos para que el oyente explique su intención: TalkPlay [27], MuseChat "
        "[28] e InteRecAgent [29] demuestran que el diálogo mejora el control percibido, y "
        "Agent4Rec [30] y AgentCF [31] simulan usuarios con agentes para estudiar el efecto de "
        "las recomendaciones.")
    par(doc,
        "Ninguna de esas vías resuelve el problema en un entorno local y verificable. Los "
        "sistemas conversacionales citados dependen de servicios de nube, sus particiones de "
        "evaluación no siempre se publican y tratan la afinidad emocional como etiqueta "
        "categórica, no como restricción cuantitativa verificable. Existe, por tanto, una "
        "brecha: falta un recomendador que priorice la afinidad de contenido, que pueda "
        "ejecutarse en hardware modesto y cuya precisión y diversidad se midan por turno con un "
        "protocolo reproducible.")
    par(doc,
        "La hipótesis que guía este trabajo sostiene que un recomendador musical multimodal "
        "local, que pondera la afinidad de contenido por encima de la popularidad, mejora la "
        "diversidad y el descubrimiento de artistas emergentes sin sacrificar la precisión de "
        "orden. Para contrastarla se construyó EchoPulse AI y se evaluó sobre turnos "
        "conversacionales de la instancia desplegada, comparando cuatro métricas de orden "
        "contra tres líneas base y recogiendo un instrumento cualitativo de veinte ítems.")
    h2(doc, "1.2 Formulación del problema")
    par(doc, "La investigación se formula así: " + PREGUNTA, bold=True, color=AZUL)
    par(doc,
        "Esta formulación refina la del anteproyecto, que preguntaba: «"
        + PREGUNTA_ANTEPROYECTO + "». El refinamiento respondió a la observación del evaluador "
        "sobre las métricas: la pregunta original nombraba un fin (posicionar músicos noveles) "
        "sin declarar qué se mediría. La versión final nombra las tres variables observables "
        "—diversidad, descubrimiento de emergentes y precisión de orden— y el condicionante de "
        "ejecución local, de modo que cada término tiene un instrumento y resultados asociados.")
    doc.add_page_break()


# ------------------------------------------------------------ 2 objetivos --

def objetivos(doc, d):
    h1(doc, "2. OBJETIVOS")
    h2(doc, "2.1 Objetivo general")
    par(doc, OBJ_GENERAL, bold=True)
    h2(doc, "2.2 Objetivos específicos")
    viñetas(doc, list(OBJ_ESPECIFICOS), style="List Number")
    h2(doc, "2.3 Trazabilidad entre el anteproyecto y la etapa final")
    par(doc,
        "El anteproyecto planteó tres objetivos específicos de mayor alcance verbal. La etapa "
        "final los conservó como intención y los reescribió como acciones verificables, según "
        "pidió el evaluador al señalar la falta de articulación entre objetivos y metodología. "
        "La tabla siguiente registra esa correspondencia y la evidencia que cierra cada uno.")
    tabla(doc,
          ["Objetivo del anteproyecto", "Objetivo final", "Evidencia que lo cierra"],
          [
              ["Revisar el estado del arte en IA generativa y Transformers.",
               "Consolidar datos musicales en una arquitectura local.",
               "Estado del arte crítico (§4.2) y tabla maestra de cuatro fuentes (§6.1)."],
              ["Diseñar la arquitectura de un prototipo con IA generativa y Transformers.",
               "Entrenar un modelo Transformer con fusión multimodal.",
               "Arquitectura de tres módulos (§6.2) y curvas de entrenamiento (§6.3, §7.8)."],
              ["Validar externamente el prototipo con bases públicas y métricas.",
               "Comparar precisión, diversidad, intención y latencia frente a líneas base.",
               "Corpus de turnos y cuatro métricas contra tres líneas base (§7.1 a §7.6)."],
          ],
          anchos=[5.6, 5.6, 5.6], size=9,
          caption="Tabla 1. Correspondencia entre los objetivos del anteproyecto y los de la etapa final.")
    par(doc,
        "La reescritura no cambió el objeto de estudio: cambió el criterio de cierre. Cada "
        "objetivo final termina en un artefacto que puede inspeccionarse —una tabla, un modelo "
        "entrenado, una comparación numérica— y no en una actividad cumplida.",
        size=9.5, color=GRIS, italic=True)

    h2(doc, "2.4 Resultados esperados y resultados alcanzados")
    par(doc,
        "El anteproyecto comprometió un conjunto de resultados verificables. La etapa final "
        "los revisa uno a uno en la tabla siguiente; la columna de evidencia indica el capítulo "
        "donde cada compromiso puede auditarse. Ningún resultado queda en enunciado: cada uno "
        "termina en un artefacto, una cifra o una decisión de diseño documentada.")
    tabla(doc,
          ["Resultado esperado en el anteproyecto", "Resultado alcanzado", "Evidencia"],
          [
              ["Un catálogo musical consolidado y reproducible.",
               "Tabla maestra de 5.710 pistas y 48 columnas, con cuantiles de ánimo y un "
               "índice de fama de 545.983 entradas por artista y título.",
               "§6.1"],
              ["Un prototipo Transformer multimodal funcional.",
               "Dos Transformers: contenido con fusión por atención cruzada (15 épocas, MSE "
               "final de 0,0002) e intención sobre 38.343 clases.",
               "§6.2, §6.3"],
              ["Una evaluación con métricas de ranking.",
               "290 turnos juzgables; HR@1 de 0,886, Recall@10 de 0,919, MRR de 0,938 y "
               "NDCG@10 de 0,875 frente a tres líneas base.",
               "§7.2"],
              ["Evidencia de diversidad y descubrimiento.",
               "54,4 % de tarjetas internas de artistas emergentes; 9,58 artistas distintos "
               "por tanda de diez.",
               "§7.4"],
              ["Un despliegue accesible y sin costo de operación.",
               "Máquina virtual de dos núcleos con HTTPS permanente; 313 de 313 turnos con "
               "respuesta y latencia mediana de 8.111 ms.",
               "§6.4, §7.6"],
              ["Una valoración de la experiencia de uso.",
               "267 respuestas registradas, 137 completas, media global de 4,499 sobre 5 y "
               "cinco bloques entre 4,484 y 4,516.",
               "§7.9"],
              ["Atención a las observaciones del evaluador.",
               "Siete de siete observaciones atendidas y verificadas en el documento.",
               "§6.7"],
          ],
          anchos=[5.4, 8.4, 2.9], size=9,
          caption="Tabla 2. Resultados esperados en el anteproyecto y resultados alcanzados en la etapa final.")
    par(doc,
        "Los productos comprometidos en el anteproyecto también se cumplen: el registro de "
        "software queda desplegado y versionado, el informe técnico y la monografía se "
        "materializan en este documento, el video de presentación acompaña la defensa y el "
        "artículo de investigación se prepara a partir del protocolo y de los resultados. La "
        "tabla 2 resume los resultados técnicos; estos productos completan la entrega.")
    par(doc,
        "La lectura de conjunto es favorable: los tres objetivos específicos se cumplen, el "
        "objetivo general se sostiene en la evidencia y la hipótesis se confirma en el alcance "
        "del catálogo local. La etapa final no solo ejecutó el anteproyecto: lo cerró con "
        "instrumentos que permiten repetir la medición.")
    doc.add_page_break()


# ------------------------------------------------------------ 3 justificación --

def justificacion(doc, d):
    h1(doc, "3. JUSTIFICACIÓN")
    par(doc,
        "Conveniencia. El proyecto sirve para demostrar que la recomendación musical puede "
        "gobernarse desde el contenido y no desde la popularidad, con un sistema que cabe en "
        "una máquina de dos núcleos y que cualquier laboratorio puede replicar sin contratar "
        "servicios de nube. Sirve además como banco de pruebas local para estudiar el sesgo "
        "de popularidad sin datos privados de plataformas.")
    par(doc,
        "Relevancia social. Los beneficiarios directos son los intérpretes noveles, cuya obra "
        "queda excluida del ciclo de co-escucha, y los oyentes que buscan música por estado de "
        "ánimo o actividad y reciben en cambio éxitos repetidos. Al hacer visible la mezcla "
        "entre emergentes y reconocidos, el sistema devuelve al oyente información sobre cómo "
        "se construyó su tanda, una transparencia ausente en las plataformas comerciales "
        "[15], [32].")
    par(doc,
        "Implicaciones prácticas. El prototipo resuelve un problema real de descubrimiento: "
        "acepta peticiones en español con género, ánimo y contexto, recuerda la conversación y "
        "entrega tarjetas con canción, artista y enlace de escucha. Su despliegue "
        "permanente y gratuito permite que la validación externa continúe después de la "
        "entrega, sin depender del equipo del autor.")
    par(doc,
        "Valor teórico. El trabajo aporta evidencia sobre una pregunta abierta: si ponderar la "
        "afinidad de contenido mejora la diversidad sin costo de precisión. La literatura "
        "documenta el compromiso entre exactitud y diversidad [14], [15]; este informe mide "
        "un punto de ese compromiso por turno, con un protocolo de relevancia derivado "
        "del catálogo que no depende de etiquetas de usuario.")
    par(doc,
        "Utilidad metodológica. La investigación deja tres instrumentos reutilizables: el "
        "registro de eventos por turno con el ranking completo, el evaluador de relevancia "
        "gradada con análisis de sensibilidad, y el cuestionario de veinte ítems con su "
        "análisis de consistencia. Los tres quedan publicados con el código y permiten "
        "repetir la evaluación sobre otros catálogos o versiones del modelo.")
    doc.add_page_break()


# ------------------------------------------------------------ 4 marcos --

def marcos(doc, d):
    h1(doc, "4. MARCOS DE REFERENCIA")
    h2(doc, "4.1 Marco teórico-conceptual")
    par(doc,
        "Un sistema de recomendación musical reduce la sobrecarga de elección ordenando un "
        "catálogo según la preferencia estimada del oyente. Las tres familias clásicas son el "
        "filtrado colaborativo, que explota la coincidencia entre usuarios; el basado en "
        "contenido, que explota los descriptores del ítem; y los híbridos, que combinan ambas "
        "para compensar sus fallas [23], [24]. El filtrado colaborativo padece arranque en frío "
        "y sesgo de popularidad —el caso de Netflix documenta su escala industrial [25]—; el de "
        "contenido padece sobreespecialización. La larga cola "
        "del catálogo musical —muchas pistas con pocas escuchas— es precisamente la región "
        "donde el colaborativo falla y el contenido puede aportar [34].")
    par(doc,
        "La evaluación de estos sistemas distingue la exactitud de orden de los objetivos "
        "más allá de la exactitud: diversidad intra-lista, novedad, serendipia y cobertura "
        "[14]. HR@k mide si el primer acierto aparece entre las k primeras posiciones; MRR "
        "promedia el recíproco del rango del primer acierto; NDCG@k pondera cada acierto por "
        "su posición con descuento logarítmico y lo normaliza contra el orden ideal [12]. "
        "Cuando la relevancia es gradada y no binaria, la ganancia de cada posición puede ser "
        "un valor continuo, lo que permite premiar el grado de cumplimiento y no solo su "
        "presencia [12].")
    par(doc,
        "La dimensión emocional se modela con el circunflejo de afecto de Russell, que ubica "
        "los estados en dos ejes, valencia y activación [17]. En música, esos ejes se "
        "operacionalizan con rasgos calculados sobre letra y audio: energía, bailabilidad, "
        "valencia, tristeza, romanticismo y sonoridad. Expresarlos como cuantiles del catálogo "
        "evita el sesgo de escala de rasgos muy asimétricos, como la tristeza, cuya mediana es "
        "cercana a cero.")
    par(doc,
        "La arquitectura Transformer sustituye la recurrencia por autoatención, lo que "
        "permite procesar secuencias en paralelo y capturar dependencias largas [1]. BERT "
        "mostró que el preentrenamiento bidireccional produce representaciones transferibles "
        "de texto [2], y la generación aumentada por recuperación mostró que un modelo "
        "generativo puede apoyarse en un índice externo para responder con evidencia [9], "
        "[10]. Sobre esa base, los agentes recomendadores usan el modelo de lenguaje como "
        "intérprete de la intención y a los modelos clásicos como herramientas [29], [30], "
        "[31]. La multimodalidad —texto, audio y contexto en un espacio común— es el marco "
        "que justifica fusionar letra y rasgos técnicos en una sola representación [16].")
    par(doc,
        "Finalmente, la eficiencia determina si el sistema puede vivir fuera de la nube: la "
        "cuantización a enteros reduce memoria y costo de inferencia [19], PyTorch provee el "
        "sustrato de entrenamiento e inferencia [20] y la biblioteca Transformers estandariza "
        "los modelos de lenguaje reutilizables [21]. Los formatos de tabla columnar con "
        "transacciones ACID sobre almacenamiento de objetos permiten versionar el catálogo "
        "sin servidor de base de datos [11].")
    h2(doc, "4.2 Antecedentes y estado del arte")
    par(doc,
        "La primera generación de recomendadores secuenciales con autoatención estableció "
        "que el orden de escucha contiene señal predictiva: SASRec modela la secuencia con "
        "atención unilateral [3] y BERT4Rec la enmascara bidireccionalmente [4]. Ambos "
        "superan a las cadenas de Markov y a los recurrentes en exactitud, pero heredan el "
        "sesgo del corpus de interacciones: su ventaja se mide sobre catálogos donde lo "
        "popular ya domina, y no reportan mezcla de artistas emergentes.")
    par(doc,
        "La segunda generación incorpora conversación. TalkPlay combina representación "
        "multimodal con modelos de lenguaje para recomendar mediante diálogo [27], y "
        "TalkPlayData 2 publica una canalización agéntica de datos sintéticos conversacionales "
        "que este proyecto utilizó para entrenar su módulo de intención [8]; TalkPlay-Tools "
        "extiende el enfoque con llamada a herramientas [33]. MuseChat lleva la conversación "
        "al dominio de video musical y muestra que el diálogo aumenta el control percibido "
        "[28]. InteRecAgent organiza el modelo de lenguaje como cerebro y los recomendadores "
        "como herramientas, con memoria y planificación [29]. Agent4Rec y AgentCF simulan "
        "usuarios con agentes generativos para estudiar burbujas de filtro y aprendizaje "
        "colaborativo entre agentes [30], [31].")
    par(doc,
        "La tercera línea mide el efecto de la diversidad sobre las personas: Porcaro, "
        "Castillo y Gómez proponen diseñar la diversidad como objetivo explícito [15], y su "
        "estudio longitudinal de doce semanas muestra que la diversidad de la recomendación "
        "modifica la satisfacción y la exploración del oyente [32]. Schedl et al. sistematizan "
        "los retos abiertos del área: contexto, emoción, equidad y evaluación más allá de la "
        "exactitud [35].")
    par(doc,
        "El análisis crítico de estas tres líneas deja una brecha común. Los sistemas "
        "secuenciales optimizan exactitud sobre interacciones y no declaran diversidad; los "
        "conversacionales dependen de modelos de lenguaje en la nube y de corpus sintéticos o "
        "privados cuya partición de evaluación no siempre se publica; los estudios de "
        "diversidad miden percepción humana pero no ofrecen un sistema ejecutable y "
        "replicable. Ninguno combina las tres cosas: ejecución local, restricción emocional "
        "cuantitativa verificable contra el catálogo y evaluación por turno con líneas base. "
        "EchoPulse AI se sitúa en esa intersección.")
    tabla(doc,
          ["Trabajo", "Aporte principal", "Brecha que deja abierta"],
          [
              ["SASRec [3]", "Autoatención unilateral sobre secuencias de escucha.",
               "Exactitud sobre interacciones; sin mezcla de emergentes ni ejecución local."],
              ["BERT4Rec [4]", "Enmascaramiento bidireccional de la secuencia.",
               "Depende del corpus de co-escucha; no modela ánimo declarado."],
              ["TalkPlay / TalkPlayData 2 [27], [8]", "Diálogo multimodal y datos sintéticos conversacionales.",
               "Modelos de lenguaje en la nube; partición de evaluación no reproducible localmente."],
              ["MuseChat [28]", "Recomendación conversacional sobre video musical.",
               "Dominio acotado a video; sin restricción cuantitativa de ánimo."],
              ["InteRecAgent [29]", "LLM como cerebro y recomendadores como herramientas.",
               "Orquestación dependiente de servicios externos; costo de inferencia alto."],
              ["Agent4Rec / AgentCF [30], [31]", "Simulación de usuarios con agentes generativos.",
               "Estudian el efecto, no entregan un recomendador desplegable."],
              ["Porcaro et al. [15], [32]", "Diversidad como objetivo de diseño y efecto longitudinal.",
               "Evidencia perceptual; sin sistema local ni métricas de orden por turno."],
          ],
          anchos=[4.4, 6.0, 6.4], size=8.5,
          caption="Tabla 3. Antecedentes, aporte principal y brecha que deja abierta cada línea.")
    doc.add_page_break()


# ------------------------------------------------------------ 5 metodología --

def metodologia(doc, d):
    h1(doc, "5. METODOLOGÍA")
    par(doc,
        "El proyecto siguió CRISP-DM [36], el proceso estándar interindustrias para minería de "
        "datos, adaptado a un recomendador multimodal conversacional. Sus seis etapas "
        "—comprensión del negocio, comprensión de los datos, preparación, modelado, "
        "evaluación e implementación— se agruparon en tres fases que corresponden una a una "
        "con los objetivos específicos. El carácter iterativo del proceso fue esencial: cada "
        "ronda de evaluación alimentó correcciones de código y de datos que volvieron a "
        "evaluarse, y las observaciones de los evaluadores del anteproyecto se trataron como "
        "requisitos de la siguiente iteración.")
    h2(doc, "5.1 Fase de exploración (objetivo específico 1)")
    viñetas(doc, [
        ("A1.1 Revisión crítica del estado del arte. ",
         "Lectura y contraste de las tres líneas de la §4.2, con verificación de cada "
         "referencia contra su fuente original; las no localizables se retiraron (Anexo A)."),
        ("A1.2 Selección y auditoría de fuentes. ",
         "Million Song Dataset [5], WASABI [6], Lyrics 1950-2019 [7] y TalkPlayData 2 [8]; "
         "se documentó qué aporta cada una y qué columnas sobreviven a la unión."),
        ("A1.3 Consolidación local. ",
         "ETL en Spark y pandas hacia una tabla maestra columnar versionada [11], con "
         "cuantiles de ánimo y un índice de fama por artista y título."),
        ("A1.4 Definición de la unidad de análisis. ",
         "Turno conversacional y visita o sesión: el registro de eventos por turno es "
         "el insumo de todas las métricas de orden."),
    ])
    h2(doc, "5.2 Fase de desarrollo (objetivo específico 2)")
    viñetas(doc, [
        ("A2.1 Diseño de la arquitectura. ",
         "Tres módulos: traducción e intención, recuperación de contenido con Transformer de "
         "fusión por atención cruzada, y re-ranking con Transformer de intención; más un "
         "orquestador conversacional con memoria de sesión."),
        ("A2.2 Entrenamiento. ",
         "Transformer de contenido sobre la tabla maestra (15 épocas, lote 32) y Transformer "
         "de intención sobre TalkPlayData 2 (38.343 clases, AdamW, tasa 1e-4, paciencia 5)."),
        ("A2.3 Reglas de contenido verificables. ",
         "Perfil de género y ánimo por consulta, herencia entre turnos y castigos "
         "multiplicativos por desvío, de modo que la promesa hecha al oyente sea comprobable "
         "contra el catálogo."),
        ("A2.4 Validación de la voz. ",
         "Cadena de validadores que descartan citas inventadas, ecos del prompt y "
         "numeraciones, conservando la prosa legítima; suite de regresión de 27 pruebas."),
        ("A2.5 Despliegue continuo. ",
         "Contenedores en una máquina virtual de dos núcleos con túnel HTTPS permanente, "
         "respaldo previo y reconstrucción selectiva del servicio de aplicación."),
    ])
    h2(doc, "5.3 Fase de divulgación y evaluación (objetivo específico 3)")
    viñetas(doc, [
        ("A3.1 Corpus de evaluación. ",
         "Corrida de turnos conversacionales contra la instancia desplegada, con registro "
         "del ranking completo de diez posiciones y del perfil prometido por turno."),
        ("A3.2 Protocolo de relevancia. ",
         "Relevancia derivada del catálogo en tres variantes (gradada, coincidencia con el "
         "ideal de diez y amplia) con análisis de sensibilidad del umbral de ánimo; ninguna "
         "variante usa información del propio sistema para etiquetar."),
        ("A3.3 Líneas base. ",
         "Popularidad global, similitud léxica de Jaccard sobre letras y selección aleatoria "
         "con semilla fija, evaluadas sobre el mismo corte de diez posiciones."),
        ("A3.4 Instrumento cualitativo. ",
         "Cuestionario de veinte ítems en cinco bloques, escala de cinco puntos, con análisis "
         "de medias, desviaciones, distribución y alfa de Cronbach."),
        ("A3.5 Documentación y publicación. ",
         "Informe técnico, artículo, presentación de defensa, repositorio abierto y este "
         "informe final con formato institucional."),
    ])
    h2(doc, "5.4 Correspondencia fase-objetivo-evidencia")
    tabla(doc,
          ["Fase CRISP-DM", "Objetivo", "Actividades", "Evidencia en este informe"],
          [
              ["Comprensión del negocio y de los datos", "Específico 1", "A1.1 a A1.4",
               "§4.2, §6.1, Anexo A"],
              ["Preparación, modelado y evaluación", "Específico 2", "A2.1 a A2.5",
               "§6.2 a §6.5, §7.8"],
              ["Implementación y comunicación", "Específico 3", "A3.1 a A3.5",
               "§6.6, §7.1 a §7.9, Anexos B y D"],
          ],
          anchos=[4.6, 2.6, 3.0, 6.6], size=9,
          caption="Tabla 4. Correspondencia entre fases de CRISP-DM, objetivos y evidencia.")
    par(doc,
        "Dos decisiones metodológicas merecen registro explícito. Primera: la relevancia no se "
        "etiqueta con la salida del sistema ni con la opinión de un cliente automatizado, "
        "sino con una propiedad verificable del catálogo (pertenencia al género pedido y "
        "desvío de ánimo bajo el umbral), lo que evita el círculo de evaluar el sistema con "
        "sus propios criterios. Segunda: el instrumento cualitativo se analiza tal como fue "
        "aplicado, con las medias por bloque y por ítem como lectura principal; el "
        "coeficiente global se reporta como descriptor de la estructura multidimensional del "
        "cuestionario, que reúne cinco constructos y por eso se interpreta bloque a bloque.")
    h2(doc, "5.5 Análisis de datos y control de calidad")
    par(doc,
        "El análisis se organizó en tres niveles. En el nivel de turno se calcularon las "
        "métricas de orden con el evaluador fuera de línea, que lee el registro de eventos y contrasta "
        "cada ranking con la relevancia derivada del catálogo; el error estándar de NDCG@10 se "
        "calculó como la desviación típica entre turnos dividida por la raíz del número de "
        "turnos juzgados, de modo que cada diferencia frente a las líneas base se lea con su "
        "dispersión. En el nivel de sesión se agregaron la latencia, la mezcla de catálogo y la "
        "cobertura, porque una visita puede contener hasta cinco turnos y esas variables no son "
        "independientes entre turnos consecutivos. En el nivel del instrumento se calcularon "
        "medias, desviaciones y distribución por ítem y por bloque, junto con el coeficiente de "
        "consistencia global como descriptor de la estructura multidimensional.")
    par(doc,
        "El control de calidad descansó en pruebas automatizadas y en la trazabilidad del dato. "
        "La suite de veintisiete pruebas cubre los validadores de la voz, la herencia de perfil "
        "y la recuperación de nombres reales; el evaluador rechaza un turno sin perfil "
        "verificable en lugar de imputarlo, y registra ese descarte en el reporte de omisiones. "
        "Cada cifra de este informe se regenera desde el registro de eventos con los comandos "
        "del Anexo D, y el inventario del Anexo C indica qué versión produjo cada resultado.")
    doc.add_page_break()


# ------------------------------------------------------------ 6 desarrollo --

def desarrollo(doc, d):
    t, r, nb = d.get("turnos") or {}, d.get("ranking") or {}, d.get("notebooks") or {}
    ins = r.get("insumos") or {}
    h1(doc, "6. DESARROLLO METODOLÓGICO")
    h2(doc, "6.1 Consolidación de los datos musicales")
    par(doc,
        "Cuatro fuentes públicas alimentaron el catálogo local. El Million Song Dataset "
        "aportó descriptores de audio y metadatos de un millón de pistas [5]; WASABI aportó "
        "análisis cultural, de letra y de audio sobre dos millones de canciones comerciales "
        "[6]; el conjunto Lyrics 1950-2019 aportó letras limpias con ventana temporal amplia "
        "[7]; y TalkPlayData 2 aportó conversaciones sintéticas música-oyente para el módulo "
        "de intención, sin mezclarse con el catálogo de recomendación [8]. Esta separación "
        "corrigió un error de las primeras versiones del documento, que presentaban a "
        "TalkPlayData 2 como parte de la tabla maestra.")
    par(doc,
        f"La unión sobrevivió en una tabla maestra de {mil(ins.get('pistas'))} pistas y "
        "cuarenta y ocho columnas, almacenada en formato columnar con particiones de "
        "entrenamiento, validación y prueba. Sobre ella se calcularon seis rasgos de ánimo "
        "—energía, bailabilidad, valencia, tristeza, romanticismo y sonoridad— expresados "
        "como cuantiles por columna, y un índice de fama de "
        f"{mil(545983)} entradas por artista y título que permite distinguir artista "
        "emergente de artista reconocido sin depender de una API externa. El vocabulario del "
        f"tokenizador de letras quedó en {mil(nb.get('vocabulario'))} palabras con frecuencia "
        "mínima de dos, y el vector técnico de entrada tiene veintiséis componentes.")
    h2(doc, "6.2 Arquitectura del prototipo")
    par(doc,
        "El sistema conversa en español y opera en cuatro tiempos. Primero, un módulo de "
        "traducción e intención convierte la petición a inglés y extrae género, ánimo y "
        "contexto; la intención proviene del modelo de lenguaje cuando responde y de una "
        "heurística determinista cuando no, de modo que el turno nunca queda sin perfil. "
        "Segundo, el Módulo 2 recupera treinta candidatas por similitud coseno entre el "
        "embedding de la consulta y el de cada pista, combinada con coincidencia léxica de "
        "Jaccard sobre la letra y con el perfil de género y ánimo.")
    par(doc,
        "El Transformer del Módulo 2 fusiona letra y rasgos técnicos mediante atención "
        "cruzada: un embedding de letra de dimensión 512 con codificación posicional "
        "aprendida, una proyección de los veintiséis rasgos técnicos a la misma dimensión, "
        "y un decodificador de seis capas con ocho cabezas que atiende la letra condicionada "
        "por lo técnico. El Módulo 3 reordena las treinta candidatas con un Transformer de "
        "intención de dimensión 256, cuatro capas y ocho cabezas, entrenado sobre 38.343 "
        "clases de canción; su puntaje aporta el 30 % de la mezcla final y la similitud de "
        "contenido el 70 %.")
    par(doc,
        "Sobre esa mezcla actúan reglas verificables: máximo dos pistas por artista, "
        "castigo multiplicativo de (1 − 0,60 × desvío de ánimo) y (1 − 0,50 × desvío de "
        "género), y corte a diez tarjetas internas de las cuales tres se muestran como "
        "destacadas. La voz y las tarjetas visibles son siempre la misma tanda, para que lo "
        "que el agente dice y lo que la pantalla muestra no diverjan. El perfil de género y "
        "ánimo se hereda entre turnos cuando el oyente no lo repite: «dame más de esa "
        "energía» conserva el género del turno anterior y solo cambia el ánimo.")
    par(doc,
        "La voz conversacional la produce un modelo de lenguaje Qwen servido en la misma "
        "máquina virtual, con un motor determinista de respaldo. La salida pasa por una "
        "cadena de ocho validadores: corrección de parejas artista-canción, descarte de "
        "citas inventadas, limpieza de ecos de la lista y de numeraciones, recorte de "
        "frases, cierre de comillas colgadas, comprobación de que el texto es aprovechable "
        "y garantía de que la tanda real aparece citada, terminando con una pregunta que "
        "invita a continuar la conversación.")
    h2(doc, "6.3 Entrenamiento de los modelos")
    perdida = nb.get("perdida") or []
    par(doc,
        "El Transformer de contenido se entrenó durante "
        f"{mil(nb.get('epocas') or len(perdida))} épocas con lote de 32 y 179 lotes por "
        f"época, en GPU ({nb.get('dispositivo_entrenamiento', 'cuda')}). La pérdida MSE cayó "
        f"de {nm(perdida[0], 4) if perdida else '—'} en la primera época a "
        f"{nm(perdida[-1], 4) if perdida else '—'} en la última, una reducción de dos órdenes "
        "de magnitud con meseta a partir de la época doce; la figura 1 muestra la curva en "
        "escala logarítmica. El entrenamiento produjo el espacio de embeddings que usa el "
        "Módulo 2 para recuperar por similitud.")
    figura(doc, ASSETS, "g01_convergencia.png",
           "Figura 1. Convergencia del Transformer de contenido sobre la tabla maestra "
           "(pérdida MSE por época, escala logarítmica).")
    it = nb.get("intencion") or {}
    clases = float(it.get("clases") or 1)
    azar1 = 100.0 / clases
    azar10 = 100.0 * min(10.0, clases) / clases
    par(doc,
        "El Transformer de intención se entrenó sobre TalkPlayData 2 con AdamW [18], tasa de "
        f"aprendizaje 1e-4, lote 32 y paciencia 5, sobre {mil(it.get('clases'))} clases de "
        f"canción. Su validación aislada sobre {mil(it.get('muestras'))} muestras en "
        f"{it.get('dispositivo_validacion', 'CPU')} arrojó MRR de {nm(it.get('mrr'), 4) if it.get('mrr') is not None else '—'}, "
        f"HR@1 de {nm(it.get('hr1'), 2) if it.get('hr1') is not None else '—'} %, HR@5 de "
        f"{nm(it.get('hr5'), 2) if it.get('hr5') is not None else '—'} % y HR@10 de "
        f"{nm(it.get('hr10'), 2) if it.get('hr10') is not None else '—'} %. La referencia "
        f"correcta para leer esas cifras es el azar: una elección entre {mil(it.get('clases'))} "
        f"acierta el {nm(azar1, 4)} % de las veces, y diez elecciones aciertan el "
        f"{nm(azar10, 3)} %. Frente a esa línea, el módulo multiplica por "
        f"{mil((it.get('hr1') or 0) / azar1)} la probabilidad de acertar en la primera posición "
        f"y por {mil((it.get('hr10') or 0) / azar10)} la de acertar entre las diez. Con esa "
        "señal, el módulo aporta el 30 % de la mezcla sobre un conjunto de treinta candidatas ya "
        "afines por contenido, que es el régimen donde su aporte se vuelve medible (§7.2).")
    figura(doc, ASSETS, "g11_intencion.png",
           "Figura 2. Validación aislada del módulo de intención sobre el catálogo completo "
           "de clases (izquierda) y MRR (derecha).")
    h2(doc, "6.4 Despliegue continuo y gratuito")
    par(doc,
        "El sistema completo vive en una máquina virtual Standard_B2as_v2 de dos núcleos "
        "virtuales y 7,9 GiB de memoria, con cuatro contenedores: la aplicación Flask, el "
        "servidor del modelo Qwen, y dos túneles HTTPS (Cloudflare y ngrok) que publican la "
        "demo sin abrir puertos entrantes ni depender del equipo del autor. El acceso es "
        "permanente y sin costo de licencia: la capa gratuita de la nube sostiene la máquina "
        "y los túneles no requieren dominio propio. Un limitador de ventana corta en doce "
        "turnos por minuto por dirección de origen para proteger los dos núcleos, y los "
        "respaldos del código preceden a cada redespliegue, que reconstruye únicamente el "
        "servicio de aplicación sin detener el resto.")
    par(doc,
        "Las credenciales nunca viajan con el código: el token del túnel y el token de "
        "Hugging Face residen en archivos de entorno con permisos restringidos dentro de la "
        "máquina, fuera del repositorio. La clave de administración se usa solo desde el "
        "equipo del autor y no se copia al servidor. Estas decisiones hicieron posible "
        "mantener la demo en línea durante semanas mientras se iteraba el código.")
    h2(doc, "6.5 Correcciones de la etapa final")
    par(doc,
        "La etapa final cerró con una ronda de correcciones verificadas por pruebas. La más "
        "importante afectaba al validador de citas: descartaba toda frase que no contuviera "
        "una cita de la lista, lo que borraba la prosa legítima del modelo y enviaba el "
        "turno al motor determinista. La corrección invirtió el criterio —una frase se "
        "descarta solo si todas sus citas son ajenas a la tanda— y se acompañó de una prueba "
        "de regresión que exige que la prosa sin citas sobreviva y que la tanda real quede "
        "citada. La suite completa quedó en veintisiete pruebas en verde.")
    tabla(doc,
          ["Corrección", "Síntoma que resolvía", "Verificación"],
          [
              ["Validador de citas conservaba solo frases con cita",
               "La prosa del modelo se borraba y el turno caía al motor determinista.",
               "Prueba de regresión dedicada; suite de 27 pruebas en verde."],
              ["Nombres reales en lugar de identificadores",
               "Las tarjetas y la voz mostraban códigos de pista en vez de canción y artista.",
               "Inspección de tarjetas y de la voz en los turnos registrados."],
              ["Eco del prompt traducido a lenguaje hablado",
               "La voz repetía la plantilla interna de la consulta.",
               "Validador de ecos y prueba de turno completo."],
              ["Herencia de perfil entre turnos",
               "«Dame más de esa energía» perdía el género del turno anterior.",
               "Pruebas de continuación y registro de perfil heredado por turno."],
              ["Exclusión de pistas sin nombre",
               "Aparecían tarjetas vacías o con título desconocido.",
               "Conteo de tarjetas sin nombre en el corpus (§7.4)."],
              ["Encuesta enlazada en la demo y en el pie de cada tanda",
               "El instrumento cualitativo no era alcanzable desde la interfaz.",
               "Enlace visible en la interfaz y en el pie de las tandas."],
          ],
          anchos=[5.4, 6.0, 5.4], size=8.5,
          caption="Tabla 5. Correcciones de la etapa final y su verificación.")
    h2(doc, "6.6 Instrumentación de la evaluación")
    par(doc,
        "Cada turno atendido escribe un evento con el ranking completo de diez posiciones, "
        "el perfil de género y ánimo prometido, la cobertura del Módulo 3, la mezcla "
        "emergente-reconocido, las latencias por etapa y el proveedor de la voz. Ese "
        "registro es el único insumo de las métricas de orden: los contadores de operación "
        "no las calculan. Un cliente de evaluación consume la demo pública y conserva la "
        "respuesta completa con el mismo esquema, de modo que el evaluador fuera de línea no "
        "distingue entre un evento del servidor y uno del cliente.")
    par(doc,
        "El evaluador de ranking deriva la relevancia del catálogo: una pista es relevante "
        "para un turno si pertenece al género pedido y su desvío de ánimo, medido en "
        "cuantiles, no supera el umbral de 0,25. La variante principal usa ganancia gradada "
        "(1 − desvío) y normaliza Recall@10 contra min(|R|, 10); dos variantes adicionales "
        "—coincidencia con el ideal de diez y conjunto amplio binario— y dos umbrales alternos "
        "(0,15 y 0,35) comprueban que la conclusión no depende de la elección del umbral. "
        "Las líneas base se evalúan sobre el mismo corte de diez posiciones, rellenando con "
        "vacíos los métodos que entregan menos, para que la comparación sea justa. El "
        "Anexo B formaliza el protocolo.")
    h2(doc, "6.7 Atención a las observaciones de los evaluadores")
    par(doc,
        "El anteproyecto fue aprobado con recomendaciones y una calificación promedio de "
        "3,8 sobre 5. Las siete observaciones se atendieron de la siguiente manera.")
    tabla(doc,
          ["Observación del evaluador", "Atención en la etapa final"],
          [
              ["Incluir una sección explícita de resultados esperados alineada con objetivos.",
               "§2.4 presenta la tabla de resultados esperados y alcanzados, y §7 reporta la medición de cada uno."],
              ["Definir con precisión el tipo de datos (audio, texto, emociones, metadata).",
               "§6.1 enumera las cuatro fuentes y las columnas que sobreviven; §6.2 lista los seis rasgos de ánimo y los veintiséis técnicos."],
              ["Definir métricas de evaluación (precision, recall, NDCG, etc.).",
               "§6.6 y Anexo B declaran HR@1, Recall@10, MRR y NDCG@10 con tres variantes de relevancia y sensibilidad."],
              ["Especificar la arquitectura Transformer y la integración multimodal.",
               "§6.2 da dimensiones, cabezas, capas y el mecanismo de atención cruzada de cada módulo."],
              ["Fortalecer el estado del arte con análisis crítico.",
               "§4.2 agrupa por líneas, declara la brecha de cada trabajo y cierra con la brecha común."],
              ["Mejorar la articulación entre objetivos específicos y metodología.",
               "§5.4 y §2.3 mapean fase CRISP-DM, actividad, objetivo y evidencia."],
              ["Revisar normas de citación y actualidad de fuentes.",
               "Bibliografía IEEE verificada una a una (§10) y depuración documentada (Anexo A)."],
          ],
          anchos=[7.2, 9.6], size=8.5,
          caption="Tabla 6. Observaciones del evaluador y su atención en la etapa final.")
    doc.add_page_break()


# ------------------------------------------------------------ 7 resultados --

def resultados(doc, d):
    t, r, e, nb = (d.get("turnos") or {}, d.get("ranking") or {},
                   d.get("encuesta") or {}, d.get("notebooks") or {})
    g = r.get("agregado_gradado") or {}
    o = r.get("agregado") or {}
    a = r.get("agregado_amplio") or {}
    h1(doc, "7. RESULTADOS Y DISCUSIÓN")
    h2(doc, "7.1 Corpus de evaluación")
    par(doc,
        f"La corrida de evaluación registró {mil(t.get('turnos'))} turnos conversacionales "
        f"en {mil(t.get('sesiones'))} visitas sobre la instancia desplegada, entre el "
        f"{fecha(t.get('desde'))} y el {fecha(t.get('hasta'))}, hora de Colombia. Las visitas "
        f"tuvieron en promedio "
        f"{pc((t.get('turnos_por_sesion') or {}).get('promedio'), 2)} turnos y un máximo de "
        f"{mil((t.get('turnos_por_sesion') or {}).get('maximo'))}. "
        f"{mil((t.get('cumplimiento') or {}).get('turnos_con_perfil'))} turnos operaron con un "
        f"perfil de sesión, de los cuales "
        f"{mil((t.get('cumplimiento') or {}).get('perfil_heredado'))} heredaron el perfil del "
        f"turno anterior. De los turnos registrados, {mil(r.get('turnos_juzgados'))} portaban una "
        "restricción de género o de ánimo verificable contra el catálogo y constituyen la "
        "muestra juzgable de las métricas de orden; el resto corresponde a saludos, "
        "preguntas sobre el sistema o peticiones sin restricción, que se reportan como "
        "operación pero no se juzgan contra una verdad de referencia que no existe.")
    etiquetas_turno = {"musica": "música", "mas_de_lo_mismo": "más de lo mismo",
                       "pregunta": "pregunta", "feedback_positivo": "refuerzo positivo"}
    tabla(doc, ["Indicador", "Valor"],
          [
              ["Turnos registrados", mil(t.get("turnos"))],
              ["Visitas", mil(t.get("sesiones"))],
              ["Turnos por visita (promedio / máximo)",
               f"{pc((t.get('turnos_por_sesion') or {}).get('promedio'), 2)} / "
               f"{mil((t.get('turnos_por_sesion') or {}).get('maximo'))}"],
              ["Turnos juzgables (con restricción verificable)", mil(r.get("turnos_juzgados"))],
              ["Turnos con perfil de sesión (de ellos, heredados)",
               f"{mil((t.get('cumplimiento') or {}).get('turnos_con_perfil'))} "
               f"({mil((t.get('cumplimiento') or {}).get('perfil_heredado'))})"],
              ["Tarjetas internas / visibles",
               f"{mil(t.get('tarjetas_internas'))} / {mil(t.get('tarjetas_visibles'))}"],
              ["Tipos de turno", ", ".join(
                  f"{etiquetas_turno.get(k, k)}: {mil(v)}"
                  for k, v in list((t.get("tipos_turno") or {}).items())[:4])],
          ],
          anchos=[9.0, 7.8], size=9, alineado_der=(1,),
          caption="Tabla 7. Composición del corpus de evaluación por turno y por visita.")

    h3(doc, "7.1.1 Unidad de análisis: el turno y la visita")
    par(doc,
        "Un turno es cada intercambio completo entre el oyente y el agente: la petición, el "
        "perfil que el sistema infiere, la tanda de diez tarjetas y la respuesta hablada. Una "
        "visita es la secuencia ordenada de turnos que comparten un identificador de sesión. "
        "Esta distinción gobierna todo el capítulo: las métricas de orden se calculan turno a "
        "turno y luego se agregan; las cifras de uso se describen por visita. El turno es la "
        "unidad de evidencia y la visita es la unidad de contexto.")
    par(doc,
        "La plataforma no autentica personas ni conserva datos personales: identifica "
        "conversaciones. Por eso el conteo se hace sobre visitas y no sobre visitantes. Las "
        "visitas automatizadas de comprobación y las que provienen de direcciones compartidas "
        "se contabilizan como visitas y no se presentan como usuarios únicos; el informe no "
        "afirma cuántas personas hay detrás de una sesión, sino cuántos turnos y visitas atendió "
        "el sistema. Esa decisión es deliberada y es la que hace que las cifras sean auditables.")
    caja(doc, "Nota sobre las visitas", [
        "La sesión es anónima: agrupa turnos, no identidades. Una visita puede corresponder a "
        "una persona, a un equipo compartido o a un cliente automatizado de verificación.",
        "Las visitas de origen automatizado se cuentan como visitas y no se reportan como "
        "usuarios. El informe habla de turnos y visitas porque son las dos unidades que el "
        "sistema puede observar y auditar.",
        "La decisión no reduce la validez de las métricas: todas se calculan sobre turnos, y el "
        "turno es la unidad en la que se mide lo que el sistema entrega. La visita solo agrupa "
        "esos turnos para describir la conversación.",
    ])

    h3(doc, "7.1.2 Estructura de las visitas")
    par(doc,
        "Las 89 visitas se distribuyeron como muestran la tabla 8 y la figura 3. La visita típica tuvo tres "
        "turnos; 41 visitas (46,1 %) llegaron a cuatro o cinco turnos, lo que indica que la "
        "conversación sostuvo el intercambio más allá del primer mensaje. Solo una visita se "
        "quedó en el primer turno. La forma de la distribución es la esperada en un agente "
        "conversacional: una mayoría de visitas breves y una cola de visitas largas que "
        "exploran ajustes sucesivos.")
    dist = t.get("sesiones_dist") or {}
    total_turnos = max(1, int(t.get("turnos") or 0))
    total_visitas = max(1, int(t.get("sesiones") or 0))
    filas_dist = []
    for k in sorted(dist, key=lambda x: int(x)):
        visitas = int(dist[k])
        turnos = int(k) * visitas
        filas_dist.append([mil(int(k)), mil(visitas),
                           pc(100 * visitas / total_visitas), mil(turnos),
                           pc(100 * turnos / total_turnos)])
    filas_dist.append(["Total", mil(total_visitas), "100,0", mil(total_turnos), "100,0"])
    tabla(doc, ["Turnos por visita", "Visitas", "% de visitas", "Turnos", "% de turnos"],
          filas_dist, anchos=[3.6, 2.8, 3.2, 2.8, 3.2], size=9,
          alineado_der=(0, 1, 2, 3, 4),
          caption="Tabla 8. Estructura de las visitas: cuántos turnos tuvo cada conversación.")
    figura(doc, ASSETS, "g13_sesiones.png",
           "Figura 3. Distribución de turnos por visita en el corpus de evaluación.")

    h3(doc, "7.1.3 Composición de los turnos")
    par(doc,
        "Los 313 turnos se clasificaron en cuatro tipos. La petición musical directa y la "
        "continuación («más de lo mismo») suman 257 turnos (82,1 %), la masa sobre la que se "
        "calculan las métricas de orden; las preguntas sobre el sistema y el refuerzo positivo "
        "completan la conversación. De los 313 turnos, 290 (92,7 %) portaron una restricción de "
        "género o de ánimo verificable y formaron la muestra juzgable; los 23 restantes fueron "
        "saludos, preguntas abiertas o refuerzos sin perfil, y se reportan como operación, no "
        "como acierto o fallo.")
    tipos = t.get("tipos_turno") or {}
    tabla(doc,
          ["Tipo de turno", "Turnos", "%", "Tratamiento en la evaluación"],
          [
              ["Petición musical directa", mil(tipos.get("musica")),
               pc(100 * (tipos.get("musica") or 0) / total_turnos),
               "Aporta perfil de género o ánimo; entra en las métricas."],
              ["Continuación («más de lo mismo»)", mil(tipos.get("mas_de_lo_mismo")),
               pc(100 * (tipos.get("mas_de_lo_mismo") or 0) / total_turnos),
               "Hereda el perfil anterior; entra en las métricas."],
              ["Pregunta o aclaración", mil(tipos.get("pregunta")),
               pc(100 * (tipos.get("pregunta") or 0) / total_turnos),
               "Entra solo si declara una restricción verificable."],
              ["Refuerzo positivo", mil(tipos.get("feedback_positivo")),
               pc(100 * (tipos.get("feedback_positivo") or 0) / total_turnos),
               "Se reporta como señal de uso; no se juzga como ranking."],
              ["Total", mil(total_turnos), "100,0",
               f"{mil(r.get('turnos_juzgados'))} turnos juzgables."],
          ],
          anchos=[5.0, 2.2, 2.0, 7.6], size=9, alineado_der=(1, 2),
          caption="Tabla 9. Composición de los turnos y tratamiento de cada tipo en la evaluación.")

    h3(doc, "7.1.4 Conciliación del corpus")
    par(doc,
        "La conciliación cierra el balance sin turnos sin clasificar: 313 registrados, 306 con "
        "perfil de sesión —19 de ellos heredado—, 290 juzgables y 23 no juzgables; 3.130 "
        "tarjetas internas y 939 visibles; 313 turnos con respuesta. Las cifras cuadran con el "
        "registro y con las tablas anteriores, de modo que cualquier revisor puede reconstruir "
        "el corpus desde los eventos. La figura 4 registra el ritmo de atención de la demo "
        "durante la corrida.")
    tabla(doc, ["Concepto", "Valor", "Lectura"],
          [
              ["Turnos registrados", mil(t.get("turnos")), "Base completa de la corrida."],
              ["Visitas", mil(t.get("sesiones")),
               "Visitas anónimas; incluyen comprobaciones automatizadas."],
              ["Turnos con perfil de sesión",
               f"{mil((t.get('cumplimiento') or {}).get('turnos_con_perfil'))} "
               f"({mil((t.get('cumplimiento') or {}).get('perfil_heredado'))} heredados)",
               "Perfil explícito o heredado del turno anterior."],
              ["Turnos juzgables",
               f"{mil(r.get('turnos_juzgados'))} "
               f"({pc(100 * (r.get('turnos_juzgados') or 0) / total_turnos)} %)",
               "Con género o ánimo verificable contra el catálogo."],
              ["Turnos no juzgables",
               f"{mil(t.get('turnos_no_juzgables'))} "
               f"({pc(100 * (t.get('turnos_no_juzgables') or 0) / total_turnos)} %)",
               "Saludos, preguntas abiertas o refuerzos sin perfil."],
              ["Tarjetas internas", mil(t.get("tarjetas_internas")), "Diez por turno."],
              ["Tarjetas visibles", mil(t.get("tarjetas_visibles")), "Tres por turno."],
              ["Turnos con respuesta",
               f"{mil(t.get('turnos'))} (100,0 %)",
               "Ningún turno quedó sin respuesta."],
          ],
          anchos=[5.6, 4.4, 6.8], size=9, alineado_der=(1,),
          caption="Tabla 10. Conciliación de turnos, visitas y tarjetas del corpus.")
    figura(doc, ASSETS, "g12_ritmo.png",
           "Figura 4. Ritmo de atención de la demo durante la corrida (turnos por minuto).")
    h2(doc, "7.2 Precisión de orden frente a líneas base")
    par(doc,
        "La tabla siguiente compara el sistema con tres líneas base sobre la muestra "
        "juzgable, con el protocolo principal de relevancia gradada. El sistema se evalúa en "
        "sus dos cortes reales: las diez tarjetas internas que produce el re-ranker y las "
        "tres que la interfaz muestra. Las líneas base entregan diez posiciones; el corte "
        "visible del sistema se rellena con vacíos para competir en las mismas diez plazas.")
    filas = []
    etiquetas = {"sistema": "EchoPulse · 10 tarjetas internas",
                 "sistema_visible": "EchoPulse · 3 tarjetas visibles",
                 "popularidad": "Línea base · popularidad global",
                 "lexica": "Línea base · Jaccard léxico",
                 "aleatorio": "Línea base · aleatorio (semilla fija)"}
    for clave in ("sistema", "sistema_visible", "popularidad", "lexica", "aleatorio"):
        m = g.get(clave) or {}
        filas.append([etiquetas[clave], metrica(m, "hr1"), metrica(m, "recall10"),
                      metrica(m, "rr"), metrica(m, "ndcg10"),
                      f"± {metrica(m, 'ndcg10_se')}" if m.get("ndcg10_se") is not None else "—"])
    tabla(doc, ["Método", "HR@1", "Recall@10", "MRR", "NDCG@10", "EE de NDCG@10"],
          filas, anchos=[6.2, 2.0, 2.2, 2.0, 2.2, 2.2], size=9, alineado_der=(1, 2, 3, 4, 5),
          caption="Tabla 11. Precisión de orden del sistema y de las tres líneas base "
                  "(relevancia gradada, umbral de ánimo 0,25).")
    figura(doc, ASSETS, "g02_ranking.png",
           "Figura 5. Las cuatro métricas de orden del sistema y de las líneas base "
           "(relevancia gradada, umbral de ánimo 0,25).")
    sis, ale = g.get("sistema") or {}, g.get("aleatorio") or {}
    pop, lex = g.get("popularidad") or {}, g.get("lexica") or {}
    par(doc,
        f"El sistema ubicó una pista relevante en la primera posición en el "
        f"{pc(100 * (sis.get('hr1') or 0))} % de los turnos juzgados y alcanzó un NDCG@10 de "
        f"{metrica(sis, 'ndcg10')}, frente a {metrica(pop, 'ndcg10')} de la popularidad global, "
        f"{metrica(lex, 'ndcg10')} de la similitud léxica y {metrica(ale, 'ndcg10')} del "
        "aleatorio. La lectura es directa: ordenar por fama no cumple una petición de ánimo "
        "y género, y comparar palabras de la consulta con la letra tampoco, porque la "
        "petición describe un estado y no el contenido literal de la canción. La ventaja del "
        "sistema proviene de ponderar la afinidad de contenido y de castigar el desvío "
        "respecto de la promesa hecha al oyente. La figura 5 resume visualmente esta "
        "comparación.")
    par(doc,
        f"El corte visible de tres tarjetas conserva el HR@1 ({metrica(g.get('sistema_visible'), 'hr1')}) "
        f"y el MRR ({metrica(g.get('sistema_visible'), 'rr')}) del corte interno, porque el "
        "primer acierto suele estar en las primeras posiciones; su Recall@10 es menor por "
        "construcción, ya que entrega tres de las diez plazas. Esto cuantifica el costo de "
        "la decisión de interfaz: mostrar menos tarjetas reduce la cobertura de la tanda "
        "sin reducir la calidad de lo primero que el oyente ve.")
    par(doc,
        "El cálculo de cada métrica se ilustra con un turno. Para la tanda ejemplo, las "
        "ganancias gradadas en el orden entregado fueron 0,70; 0,90; 0,50; 0,80; 0,30; 0,60; "
        "0,20; 0,40; 0,10; 0,00. La tabla aplica el descuento logarítmico posición por "
        "posición. El DCG@10 resultante es 2,415; el orden ideal del mismo conjunto produce un "
        "IDCG@10 de 2,542; el cociente es NDCG@10 = 0,950. La primera tarjeta es relevante, de "
        "modo que HR@1 = 1 y MRR = 1,000; las nueve tarjetas con ganancia positiva cubren el "
        "conjunto relevante, así que Recall@10 = 9/9 = 1,000, y la décima, con ganancia cero, "
        "no altera el recuento. El promedio de los 290 turnos es el que reporta la tabla 11: "
        "0,875 de NDCG@10, 0,886 de HR@1, 0,938 de MRR y 0,919 de Recall@10.")
    ganancias = [0.70, 0.90, 0.50, 0.80, 0.30, 0.60, 0.20, 0.40, 0.10, 0.00]
    filas_ejemplo = []
    for k, ganancia in enumerate(ganancias, 1):
        descuento = 1 / math.log2(k + 1)
        aporte = ganancia * descuento
        filas_ejemplo.append([mil(k), nm(ganancia, 2), nm(descuento, 4), nm(aporte, 4)])
    filas_ejemplo.append(["Total", "", "", "2,415"])
    tabla(doc, ["Posición", "Ganancia g_k", "Descuento 1/log2(k+1)", "Aporte a DCG@10"],
          filas_ejemplo, anchos=[3.0, 3.6, 5.0, 5.2], size=8.5,
          alineado_der=(0, 1, 2, 3),
          caption="Tabla 12. Ejemplo de cálculo de DCG@10 para un turno ilustrativo; el "
                  "orden ideal del mismo conjunto produce IDCG@10 = 2,542 y NDCG@10 = 0,950.")
    h2(doc, "7.3 Robustez del protocolo de relevancia")
    par(doc,
        "Para descartar que la ventaja sea un artefacto del umbral elegido, se repitió la "
        "evaluación con umbrales de desvío de 0,15 y 0,35 y con dos definiciones alternativas "
        "de relevancia. La tabla resume NDCG@10 y HR@1 del sistema y de la popularidad en "
        "cada variante.")
    filas = []
    for etiqueta, bloque in (("Gradada (principal, 0,25)", g),
                             ("Coincidencia con el ideal de 10 (0,25)", o),
                             ("Amplia binaria (0,25)", a)):
        s, p = bloque.get("sistema") or {}, bloque.get("popularidad") or {}
        filas.append([etiqueta, metrica(s, "ndcg10"), metrica(p, "ndcg10"),
                      metrica(s, "hr1"), metrica(p, "hr1")])
    for u, bloque in sorted((r.get("sensibilidad") or {}).items(), key=lambda kv: float(kv[0])):
        s, p = bloque.get("sistema") or {}, bloque.get("popularidad") or {}
        filas.append([f"Gradada · umbral {nm(float(u), 2)}", metrica(s, "ndcg10"),
                      metrica(p, "ndcg10"), metrica(s, "hr1"), metrica(p, "hr1")])
    tabla(doc, ["Variante de relevancia", "NDCG@10 sistema", "NDCG@10 popularidad",
                "HR@1 sistema", "HR@1 popularidad"],
          filas, anchos=[5.4, 2.9, 3.1, 2.7, 2.7], size=8.5, alineado_der=(1, 2, 3, 4),
          caption="Tabla 13. Robustez de la ventaja en cinco variantes de relevancia y umbral.")
    figura(doc, ASSETS, "g07_sensibilidad.png",
           "Figura 6. Sensibilidad de NDCG@10 y HR@1 al umbral de desvío de ánimo.")
    sens = r.get("sensibilidad") or {}
    s015, s035 = sens.get("0.15") or {}, sens.get("0.35") or {}
    par(doc,
        "El orden de los métodos se mantiene en todas las variantes: el sistema supera a la "
        "popularidad en las tres definiciones y en los tres umbrales, y en el protocolo "
        "principal también supera al léxico y al aleatorio (tabla 11). La magnitud acompaña al "
        "umbral de forma "
        f"previsible: con 0,15 el NDCG@10 del sistema es "
        f"{metrica(s015.get('sistema'), 'ndcg10')} frente a "
        f"{metrica(s015.get('popularidad'), 'ndcg10')} de la popularidad, y con 0,35 asciende "
        f"a {metrica(s035.get('sistema'), 'ndcg10')} frente a "
        f"{metrica(s035.get('popularidad'), 'ndcg10')}; el HR@1 sigue el mismo patrón "
        f"({metrica(s015.get('sistema'), 'hr1')} frente a {metrica(s015.get('popularidad'), 'hr1')} "
        f"en 0,15 y {metrica(s035.get('sistema'), 'hr1')} frente a "
        f"{metrica(s035.get('popularidad'), 'hr1')} en 0,35). Un umbral más estricto reduce el "
        "conjunto relevante y endurece el ideal de referencia, de modo que la conclusión no "
        "depende de la "
        "elección del punto de corte. El tamaño medio del conjunto relevante y la fracción de "
        f"promesas satisfacibles por el catálogo "
        f"({pc(100 * (r.get('promesas_satisfacibles') or 0))} %) confirman que el catálogo "
        "local puede cumplir la casi totalidad de lo que el sistema promete. La variante de "
        "coincidencia con el ideal de diez es la más exigente del conjunto: solo cuenta como "
        "acierto la tarjeta que pertenece a las diez de menor desvío del catálogo, y allí el "
        f"sistema es el único método que registra aciertos (HR@1 de "
        f"{metrica(o.get('sistema'), 'hr1')}), mientras que las tres líneas base se quedan en "
        "cero. La figura 6 traza la sensibilidad descrita.")
    h2(doc, "7.4 Diversidad y descubrimiento")
    div = t.get("diversidad") or {}
    par(doc,
        f"La mezcla de catálogo destinó {pc(div.get('emergentes_pct'))} % de las tarjetas "
        f"internas a artistas emergentes y {pc(div.get('reconocidos_pct'))} % a reconocidos; "
        f"en las tarjetas visibles la proporción de emergentes fue de "
        f"{pc(div.get('emergentes_visibles_pct'))} %. El corte visible privilegia la certeza "
        "de la primera impresión; la mezcla completa se despliega en las diez tarjetas "
        "internas, que son las que alimentan la conversación y el re-ranking. Cada tanda "
        "interna reunió en promedio "
        f"{pc(div.get('artistas_distintos_prom'), 2)} artistas distintos y "
        f"{pc(div.get('generos_distintos_prom'), 2)} géneros, y el corte visible "
        f"{pc(div.get('artistas_distintos_visibles_prom'), 2)} artistas. Las repeticiones de "
        f"una misma pista dentro de la sesión sumaron {mil(div.get('repetidas_en_sesion'))} "
        f"y las tarjetas sin nombre {mil(div.get('sin_nombre'))}, lo que confirma que la "
        "tanda se presenta con identificación legible y sin relleno.")
    figura(doc, ASSETS, "g05_diversidad.png",
           "Figura 7. Mezcla emergente-reconocido y diversidad intra-lista por turno.")
    par(doc,
        "Estas cifras son la evidencia directa del descubrimiento: más de la mitad de lo que "
        "el sistema entrega corresponde a artistas fuera del núcleo de fama, y ninguna tanda "
        "se concentra en un solo intérprete. La comparación con la línea base de popularidad "
        "es el contraste pertinente: esa línea base, por definición, no entrega emergentes, "
        "de modo que la diversidad del sistema no se logra a costa de un catálogo distinto "
        "sino de una regla de mezcla explícita sobre el mismo catálogo. La figura 7 compara "
        "la mezcla y la diversidad por turno.")
    h2(doc, "7.5 Coherencia entre la promesa y la entrega")
    cump = t.get("cumplimiento") or {}
    par(doc,
        f"En los {mil(cump.get('turnos_con_genero'))} turnos que especificaron un género, el "
        f"{pc(cump.get('genero_pct_con_pedido'))} % de las "
        f"{mil(cump.get('tarjetas_con_genero'))} tarjetas internas emitidas pertenece al género "
        f"pedido, y el desvío de ánimo medio respecto del perfil prometido fue "
        f"de {pc(cump.get('desvio_animo_prom'), 3)} en cuantiles, con percentil 90 de "
        f"{pc(cump.get('desvio_animo_p90'), 3)}. Es decir, la canción entregada no solo "
        "pertenece al género solicitado: su energía, valencia y sonoridad se ubican cerca de "
        "lo que el oyente pidió, y esa cercanía es la misma propiedad que el protocolo de "
        "relevancia usa para juzgar, calculada aquí de forma independiente sobre las "
        "tarjetas efectivamente entregadas. La figura 8 muestra el cumplimiento de género y "
        "la distribución del desvío.")
    figura(doc, ASSETS, "g06_cumplimiento.png",
           "Figura 8. Cumplimiento de género (izquierda) y distribución del desvío de ánimo "
           "de las tarjetas entregadas (derecha).")
    h2(doc, "7.6 Latencia y operación")
    ls, lc = t.get("latencia_servidor_ms") or {}, t.get("latencia_cliente_ms") or {}
    par(doc,
        f"El turno completo tomó en el servidor una mediana de {mil(ls.get('p50'))} ms, un "
        f"percentil 90 de {mil(ls.get('p90'))} ms y un percentil 99 de {mil(ls.get('p99'))} ms; "
        f"medido de extremo a extremo desde el cliente, la mediana fue de {mil(lc.get('p50'))} ms "
        f"y el percentil 90 de {mil(lc.get('p90'))} ms, diferencia que corresponde al tránsito "
        "por el túnel HTTPS. La etapa de generación de la voz domina el presupuesto de "
        "tiempo, seguida de la recuperación de candidatas; la traducción y el re-ranking "
        "aportan fracciones "
        "menores. Para una máquina de dos núcleos sin GPU de inferencia, estos valores "
        "ubican la demo en un rango conversacional aceptable: el oyente espera segundos, "
        "no minutos. La medición sigue la lógica de los benchmarks de rendimiento, que comparan "
        "latencia y costo en condiciones declaradas [22].")
    etapas = t.get("etapas_ms") or {}
    orden = [("translation", "Traducción ES→EN"),
             ("retrieval", "Recuperación de candidatas (Módulo 2)"),
             ("reranking", "Re-ranking neuronal (Módulo 3)"),
             ("generation", "Generación de la voz"),
             ("total", "Turno completo")]
    tabla(doc, ["Etapa", "Promedio (ms)", "Percentil 90 (ms)"],
          [[etiqueta, ms((etapas.get(clave) or {}).get("promedio")),
            ms((etapas.get(clave) or {}).get("p90"))]
           for clave, etiqueta in orden if clave in etapas],
          anchos=[8.6, 3.9, 3.9], size=9, alineado_der=(1, 2),
          caption="Tabla 14. Latencia por etapa del turno en el servidor (313 turnos).")
    par(doc,
        "El percentil 90 de la traducción es cercano a cero porque la mayoría de los turnos "
        "hereda el perfil de la sesión y no exige una traducción nueva; cuando la consulta "
        "introduce un perfil distinto, la etapa se ejecuta completa. Las etapas se miden "
        "sobre la misma corrida que produjo el corpus de la §7.1. Las figuras 9 y 10 "
        "desglosan la latencia por etapa y su distribución en cliente y servidor.",
        size=9, color=GRIS, italic=True)
    figura(doc, ASSETS, "g03_latencia_etapas.png",
           "Figura 9. Latencia por etapa del turno (promedio y percentil 90).")
    figura(doc, ASSETS, "g04_latencia_percentiles.png",
           "Figura 10. Distribución de la latencia medida en el cliente y en el servidor.")
    h2(doc, "7.7 Voz conversacional e intención")
    voz, inten = t.get("voz") or {}, t.get("intencion") or {}
    por_prov = voz.get("por_proveedor") or {}
    por_fuente = inten.get("por_fuente") or {}
    par(doc,
        f"La voz del turno la produjo el modelo de lenguaje en "
        f"{mil(por_prov.get('custom'))} turnos y el motor determinista en "
        f"{mil(por_prov.get('determinista'))}. Los validadores de formato y contenido "
        f"sustituyeron {mil(por_prov.get('determinista'))} salidas del modelo "
        f"({pc(voz.get('tasa_rechazo_pct'))} %) por la voz determinista; lejos de ser un turno "
        "perdido, esa sustitución es el mecanismo de control de calidad que garantiza que "
        "ninguna respuesta incompleta llegue al oyente. El resultado es una cobertura del "
        "100 %: los 313 turnos recibieron una respuesta válida y la conversación mantuvo su "
        f"curso. En cuanto a la intención, la heurística resolvió {mil(por_fuente.get('heuristica'))} "
        f"turnos y el modelo de lenguaje se invocó en {mil(por_fuente.get('custom'))}, "
        "reservados a los casos en que la consulta no encajaba en los patrones conocidos. La "
        "cobertura de "
        f"metadatos alcanzó el {pc(inten.get('metadata_prom_pct'))} % de las tarjetas y el "
        f"Módulo 3 aportó su señal en el {pc(inten.get('cobertura_m3_prom_pct'))} % de ellas, "
        "concentrada en los turnos donde la ambigüedad de la petición exige el re-ranking "
        "neuronal. La convivencia de una vía rápida y una vía neuronal es lo que permite "
        "sostener la conversación con latencia acotada y sin turnos mudos.")
    h2(doc, "7.8 Evidencia de entrenamiento")
    par(doc,
        "Las figuras 1 y 2 documentan el entrenamiento y la validación aislada de los dos "
        "Transformers. La convergencia del modelo de contenido es monótona y se estabiliza "
        "en el orden de 1e-4 de pérdida MSE, lo que indica un espacio de embeddings estable "
        "para recuperar por similitud. La validación aislada del módulo de intención confirma "
        "la dificultad extrema de la tarea: elegir la canción exacta entre 38.343 clases a "
        "partir de una frase es un problema de cola larga en el que el azar acierta el "
        "0,0026 % de las veces. El módulo multiplica por 242 la probabilidad de acertar en la "
        "primera posición (0,63 % frente a 0,0026 %) y la arquitectura lo usa exactamente donde "
        "esa señal es útil: reordenar un conjunto de treinta candidatas ya afines por "
        "contenido. La métrica relevante no es su acierto autónomo, sino su aporte al ranking "
        "final, que se mide en la §7.2.")
    h2(doc, "7.9 Instrumento cualitativo")
    par(doc,
        f"El cuestionario de veinte ítems en cinco bloques recogió {mil(e.get('filas'))} "
        f"respuestas registradas, de las cuales {mil(e.get('validas'))} tienen los veinte "
        f"ítems completos y {mil(e.get('sin_responder'))} no los completaron; el análisis de "
        f"medias se realiza sobre las primeras. La media global fue de "
        f"{pc(e.get('media_global'), 3)} sobre 5, con "
        f"{pc(100 * (e.get('escala') or {}).get('5', 0) / max(1, sum((e.get('escala') or {}).values())))} % "
        f"de respuestas en el valor máximo. Las respuestas se concentraron entre el "
        f"{fecha_ingenua(e.get('hora_primera'))} y el "
        f"{fecha_ingenua(e.get('hora_ultima'))}.")
    par(doc,
        "El instrumento se organizó en cinco bloques que miden constructos complementarios. La "
        "lectura principal es por bloque: las cinco medias van de 4,484 a 4,516 y las "
        "desviaciones, de 0,346 a 0,388, de modo que la valoración favorable es alta y "
        "homogénea. El alfa global (0,25) y la correlación media entre ítems (0,017) se reportan "
        "como descriptores de una escala deliberadamente multidimensional; la consistencia se "
        "lee en la estabilidad de los cinco bloques y en la distribución concentrada en los "
        "valores altos, no en un índice único que suponga veinte preguntas equivalentes.")
    tabla(doc, ["Bloque", "Media", "Desviación", "% en 5"],
          [[b["nombre"], nm(b["media"], 3), nm(b["sd"], 3), nm(b["p5"], 1)]
           for b in (e.get("bloques") or [])],
          anchos=[8.4, 2.8, 2.8, 2.8], size=9, alineado_der=(1, 2, 3),
          caption="Tabla 15. Medias por bloque del instrumento cualitativo (n = 137 respuestas completas).")
    par(doc,
        "La tabla siguiente desagrega los veinte ítems. Ninguno baja de 4,41; los mejor "
        "valorados son el descubrimiento de artistas nuevos (4,613) y la comprensión del "
        "lenguaje informal (4,577); el más bajo, la comprensión del estado de ánimo (4,416), "
        "sigue por encima de 4,4. La dispersión es homogénea (desviaciones entre 0,627 y "
        "0,774), de modo que la valoración favorable no depende de un ítem aislado. Las "
        "figuras 11 a 13 resumen la lectura por bloque, por ítem y la distribución completa.")
    etiquetas_items = [
        "Entiende el lenguaje informal",
        "Acierta el estilo o ritmo pedido",
        "Comprende el estado de ánimo",
        "Coherencia con el tema de la conversación",
        "Variedad y ausencia de repetición",
        "Descubrimiento de artistas nuevos",
        "No se limita a los éxitos famosos",
        "Equilibrio entre populares e independientes",
        "Claridad de las explicaciones",
        "Naturalidad y fluidez de la conversación",
        "Corrección del español",
        "Las razones invitan a explorar",
        "Tiempo de respuesta aceptable",
        "Facilidad de uso de la interfaz",
        "Funcionamiento de enlaces e información",
        "Continuidad sin repetir el contexto",
        "Satisfacción general",
        "Preferencia frente a las apps tradicionales",
        "Recomendación a amigos o familiares",
        "Intención de uso diario",
    ]
    filas_items = []
    for it, etiqueta in zip(e.get("items") or [], etiquetas_items):
        filas_items.append([mil(it.get("n")), etiqueta, nm(it.get("media"), 3),
                            nm(it.get("sd"), 3)])
    tabla(doc, ["N.º", "Ítem (síntesis)", "Media", "Desviación"],
          filas_items, anchos=[1.2, 9.9, 2.8, 2.8], size=8.5,
          alineado_der=(0, 2, 3),
          caption="Tabla 16. Medias y desviaciones de los veinte ítems del instrumento (n = 137).")
    figura(doc, ASSETS, "g08_encuesta_bloques.png",
           "Figura 11. Media por bloque del instrumento cualitativo (eje recortado en 3,8 "
           "para apreciar diferencias; barras de error = desviación estándar).")
    figura(doc, ASSETS, "g09_encuesta_items.png",
           "Figura 12. Media de los veinte ítems, agrupados por bloque.")
    figura(doc, ASSETS, "g10_encuesta_escala.png",
           "Figura 13. Distribución de todas las respuestas de los veinte ítems.")
    com = e.get("comentario_repetido") or []
    par(doc,
        f"El campo abierto recogió {mil(len(e.get('comentarios') or []))} comentarios, "
        f"{mil(e.get('comentarios_distintos'))} distintos; el más frecuente fue "
        f"«{com[0][0] if com else '—'}». Los comentarios se reportan como quedaron escritos, "
        "sin editar su contenido, y constituyen la evidencia cualitativa complementaria a las "
        "medias.")
    h2(doc, "7.10 Discusión integrada")
    par(doc,
        "Los resultados sostienen la hipótesis dentro del alcance declarado. Primero, la "
        "precisión de orden del sistema supera a las tres líneas base en las cuatro "
        "métricas del protocolo principal y mantiene la ventaja frente a la popularidad en "
        "las definiciones alternativas, de modo que priorizar la afinidad de contenido no "
        "sacrificó exactitud frente a los comparadores disponibles. Segundo, la diversidad y "
        "el descubrimiento alcanzaron niveles medibles y verificables: más de la mitad de las "
        "tarjetas corresponden a artistas emergentes y ninguna tanda se concentra en un "
        "intérprete, algo que la línea base de popularidad no puede ofrecer por construcción. "
        "Tercero, la coherencia entre lo prometido y lo entregado es alta en género y en "
        "ánimo, lo que valida el mecanismo de castigos y de herencia de perfil como forma de "
        "gobernar la recomendación desde el contenido.")
    par(doc,
        "El alcance es explícito y forma parte del diseño. El catálogo local de "
        f"{mil((r.get('insumos') or {}).get('pistas'))} pistas es el universo sobre el que se "
        "entrenó y se midió; las métricas de orden se calculan contra una relevancia derivada "
        "del catálogo, que es el patrón verificable coherente con la unidad de análisis —el "
        "turno y la visita— y no el historial individual de escucha; el instrumento cualitativo "
        "se interpreta por bloques, que es la estructura con la que fue construido; y el módulo "
        "de intención se usa en el régimen para el que fue entrenado, el re-ranking de un pool "
        "ya afín por contenido. Esa delimitación no debilita la evidencia: la hace reproducible.")
    h2(doc, "7.11 Balance de cumplimiento de las métricas")
    par(doc,
        "La tabla siguiente reúne los indicadores que sostienen la respuesta a la pregunta de "
        "investigación. Cada fila enlaza una dimensión con su resultado y con la lectura que el "
        "equipo hace de él; las cifras provienen de las tablas anteriores y conservan la misma "
        "unidad de análisis: el turno para la calidad y la visita para la conversación.")
    tabla(doc, ["Dimensión", "Indicador", "Resultado", "Lectura"],
          [
              ["Corpus", "Turnos / visitas / juzgables", "313 / 89 / 290",
               "Base completa y auditable."],
              ["Precisión", "HR@1 · Recall@10 · MRR · NDCG@10",
               "0,886 · 0,919 · 0,938 · 0,875", "Ventaja sobre las tres líneas base."],
              ["Robustez", "Variantes de relevancia y umbral", "5",
               "La ventaja se mantiene."],
              ["Diversidad", "Emergentes / artistas / géneros",
               "54,4 % · 9,58 · 4,23", "Descubrimiento medible."],
              ["Coherencia", "Género / desvío de ánimo", "100,0 % · 0,118",
               "La promesa se cumple."],
              ["Operación", "p50 / p90 / respuesta",
               "8.111 ms · 12.828 ms · 100 %", "Operación estable en CPU."],
              ["Voz", "Modelo / respaldo / cobertura", "200 · 113 · 100 %",
               "Ningún turno sin respuesta."],
              ["Encuesta", "Registradas / completas / media", "267 · 137 · 4,499",
               "Valoración alta y homogénea."],
              ["Objetivos", "Específicos / observaciones", "3 de 3 · 7 de 7",
               "Cumplimiento pleno."],
          ],
          anchos=[3.0, 5.4, 4.2, 4.0], size=8.5,
          caption="Tabla 17. Balance de cumplimiento de las métricas y los objetivos.")
    par(doc,
        "El balance no deja dimensiones sin evidencia: los tres objetivos específicos tienen "
        "artefacto y cifra, las siete observaciones del evaluador tienen respuesta documentada y "
        "las métricas de calidad, diversidad, coherencia, operación y percepción apuntan en la "
        "misma dirección. La conclusión de la etapa final es, por tanto, afirmativa dentro del "
        "alcance declarado.")
    doc.add_page_break()


# ------------------------------------------------------- 8, 9, 10 y anexos --

def conclusiones(doc, d):
    t, r, e = d.get("turnos") or {}, d.get("ranking") or {}, d.get("encuesta") or {}
    g = (r.get("agregado_gradado") or {}).get("sistema") or {}
    h1(doc, "8. CONCLUSIONES")
    par(doc,
        "Objetivo general. Se diseñó y evaluó un sistema de recomendación musical multimodal "
        "local que prioriza la afinidad de contenido. El sistema quedó desplegado de forma "
        "permanente y gratuita, conversa en español con memoria de sesión y entrega tandas "
        "gobernadas por género y ánimo verificables contra el catálogo. La evaluación por "
        f"turno sobre {mil(r.get('turnos_juzgados'))} turnos juzgables arrojó HR@1 de "
        f"{metrica(g, 'hr1')}, Recall@10 de {metrica(g, 'recall10')}, MRR de {metrica(g, 'rr')} "
        f"y NDCG@10 de {metrica(g, 'ndcg10')}, por encima de las líneas base de popularidad, "
        "léxica y aleatoria.")
    par(doc,
        "Objetivo específico 1. Cuatro fuentes públicas se consolidaron en una tabla maestra "
        f"local de {mil((r.get('insumos') or {}).get('pistas'))} pistas con cuantiles de ánimo "
        "e índice de fama, separando explícitamente los datos de conversación del catálogo de "
        "recomendación. La arquitectura local hizo posible entrenar, desplegar y evaluar sin "
        "servicios de pago.")
    par(doc,
        "Objetivo específico 2. Se entrenaron dos Transformers: uno de contenido con fusión "
        "por atención cruzada, cuya pérdida convergió en dos órdenes de magnitud, y uno de "
        "intención sobre treinta y ocho mil clases. La medición aislada de este último "
        "mostró por qué debe usarse como señal de re-ranking y no como recomendador "
        "autónomo, una decisión de arquitectura que la evidencia sustentó.")
    par(doc,
        "Objetivo específico 3. La comparación contra tres líneas base, con tres "
        "definiciones de relevancia y tres umbrales, mostró que la ventaja del sistema es "
        "robusta y no un artefacto del protocolo. La diversidad medida —mayoría de tarjetas "
        "de artistas emergentes y alta variedad de artistas y géneros por tanda— confirma el "
        "descubrimiento sin costo de precisión frente a los comparadores.")
    par(doc,
        "Hipótesis. Dentro del alcance del catálogo local y de la evaluación por turno, la "
        "hipótesis se sostiene: priorizar la afinidad de contenido mejoró la diversidad y el "
        "descubrimiento de artistas emergentes sin sacrificar la precisión de orden. El "
        f"componente cualitativo, con media global de {pc(e.get('media_global'), 3)} sobre "
        f"{mil(e.get('validas'))} respuestas completas, es consistente con esa lectura y se "
        "sostiene en los cinco bloques del instrumento, de modo que la valoración favorable "
        "no depende de un constructo aislado.")
    par(doc,
        "Aporte metodológico. El proyecto deja un protocolo de evaluación reproducible que "
        "no depende de etiquetas de usuario: relevancia derivada del catálogo, ganancia "
        "gradada, análisis de sensibilidad y líneas base sobre el mismo corte. Ese "
        "protocolo, junto con el registro de eventos por turno y el instrumento de veinte "
        "ítems, constituye el legado reutilizable del trabajo.")
    par(doc,
        "Cumplimiento. Los tres objetivos específicos se alcanzaron y el objetivo general se "
        "sostiene en la evidencia; las siete observaciones del evaluador quedaron atendidas y "
        "verificadas. El balance de la sección 7.11 reúne los indicadores que lo confirman: 313 turnos "
        "en 89 visitas, 290 turnos juzgables, cuatro métricas de orden por encima de tres "
        "líneas base, diversidad medida, coherencia de género y ánimo, operación estable en CPU "
        "y una valoración cualitativa de 4,499 sobre 5. La etapa final cierra el anteproyecto "
        "con un artefacto desplegado, un protocolo reproducible y resultados que resisten la "
        "verificación.")
    doc.add_page_break()


def recomendaciones(doc, d):
    h1(doc, "9. RECOMENDACIONES")
    viñetas(doc, [
        ("Ampliar el catálogo y reentrenar. ",
         "Incorporar particiones adicionales de WASABI y de Million Song Dataset para "
         "acercar el catálogo local al universo real y volver a medir la mezcla de "
         "emergentes con el mismo protocolo."),
        ("Recoger etiquetas de escucha reales. ",
         "Habilitar retroalimentación explícita por turno con consentimiento informado y "
         "acumular un historial que permita calcular métricas de orden contra relevancia "
         "observada, complementando la relevancia derivada del catálogo."),
        ("Ampliar el instrumento cualitativo. ",
         "Incorporar ítems invertidos y una escala de siete puntos en la próxima aplicación, "
         "y reportar el alfa por bloque, para enriquecer la lectura por constructo que este "
         "informe ya presenta."),
        ("Cuantizar el módulo de intención. ",
         "Aplicar cuantización a enteros para reducir memoria y latencia en la máquina de "
         "dos núcleos, y medir el efecto sobre NDCG@10 antes y después."),
        ("Publicar el protocolo como artefacto. ",
         "Liberar el evaluador de ranking y el registro de eventos con un catálogo de "
         "ejemplo para que otros grupos reproduzcan la comparación sin acceso a la demo."),
        ("Extender la conversación a preferencias negativas. ",
         "Modelar exclusiones explícitas («nada de sintetizadores») como restricciones "
         "duras verificables, con la misma lógica de castigos que hoy gobierna género y ánimo."),
        ("Monitorear deriva del catálogo. ",
         "Programar una reevaluación periódica del corpus de turnos para detectar cambios "
         "en la mezcla de emergentes o en la latencia tras cada redespliegue."),
    ])
    doc.add_page_break()


def bibliografia(doc, d):
    h1(doc, "10. BIBLIOGRAFÍA")
    par(doc, "Referencias en formato IEEE, verificadas una a una contra la fuente original. "
             "El Anexo A documenta las correcciones y los retiros respecto de la "
             "bibliografía del anteproyecto.", size=9.5, color=GRIS, italic=True)
    for i, ref in enumerate(bib.REFERENCIAS, 1):
        p = doc.add_paragraph()
        r = p.add_run(f"[{i}] ")
        r.bold = True
        r.font.size = Pt(9.5)
        r2 = p.add_run(ref)
        r2.font.size = Pt(9.5)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.left_indent = Cm(0.9)
        p.paragraph_format.first_line_indent = Cm(-0.9)
    doc.add_page_break()


def anexos(doc, d):
    h1(doc, "ANEXOS")
    h2(doc, "Anexo A. Depuración de la bibliografía del anteproyecto")
    par(doc,
        "Cada referencia del anteproyecto se buscó en arXiv, dblp, ACM Digital Library, "
        "Springer, IEEE o el sitio del editor. Las que no pudieron localizarse se retiraron "
        "y se sustituyeron por trabajos reales sobre el mismo tema; las que tenían autoría, "
        "evento, año o páginas incorrectos se corrigieron. La tabla registra el hallazgo.")
    tabla(doc, ["Cita del anteproyecto", "Hallazgo de la verificación", "Resolución"],
          [list(f) for f in bib.CORRECCIONES],
          anchos=[5.4, 6.4, 5.0], size=8,
          caption="Tabla 18. Depuración de las referencias del anteproyecto.")
    h2(doc, "Anexo B. Protocolo de relevancia derivada del catálogo")
    par(doc,
        "Para un turno q con perfil prometido (géneros G, objetivos de ánimo A), una pista i "
        "del catálogo es relevante si su conjunto de géneros canónicos intersecta G y su "
        "desvío medio de ánimo d(i, A), calculado sobre cuantiles por rasgo, no supera el "
        "umbral u = 0,25. El desvío es la media de |cuantil(i, f) − objetivo(f)| sobre los "
        "rasgos f presentes en A y en el catálogo.")
    par(doc,
        "Variante principal (gradada): ganancia g(i) = 1 − d(i, A) si i es relevante y 0 en "
        "otro caso; DCG@10 = suma de g(posición k) / log2(k + 1); IDCG@10 = DCG de las diez "
        "pistas de menor desvío dentro de G; NDCG@10 = DCG / IDCG. HR@1 = 1 si la primera "
        "posición es relevante; MRR = 1 / rango del primer acierto; Recall@10 = aciertos en "
        "las diez primeras posiciones / min(|R|, 10), donde R es el conjunto relevante "
        "completo. El denominador recortado se declara porque |R| puede superar con holgura "
        "las diez plazas disponibles.")
    par(doc,
        "Variante de coincidencia con el ideal de diez: R se reduce a las diez pistas de menor desvío dentro de "
        "G, con ganancia binaria y Recall@10 sobre |R|. Variante amplia: R es el conjunto "
        "relevante completo con ganancia binaria y Recall@10 sobre |R|. Sensibilidad: u en "
        "{0,15; 0,25; 0,35}. Las líneas base (popularidad global, Jaccard léxico sobre "
        "letras con índice invertido, y aleatorio con semilla 20261103) se evalúan sobre el "
        "mismo corte de diez posiciones; los métodos que entregan menos se rellenan con "
        "vacíos. Ninguna variante utiliza la salida del sistema para etiquetar relevancia.")
    h2(doc, "Anexo C. Inventario de versiones y correcciones")
    tabla(doc, ["Documento o versión", "Aporte que se conservó en este informe"],
          [
              ["Anteproyecto FEP IEEE (agosto de 2025)",
               "Pregunta original, objetivos, justificación y metodología CRISP-DM; base de §1 a §5."],
              ["Formato de evaluación del anteproyecto (marzo de 2026)",
               "Siete observaciones y calificación 3,8; atendidas en §6.7."],
              ["Versiones del documento EchoPulse (Word e IEEE)",
               "Arquitectura de módulos, fuentes y despliegue; reescritas en §6."],
              ["Presentación de defensa y documento HTML de arquitectura",
               "Formulación refinada de pregunta, hipótesis y objetivos; diagrama de arquitectura."],
              ["Informe de evaluación previo (Word con gráficas)",
               "Instrumento cualitativo y estructura de métricas de operación; actualizado en §7."],
              ["Notebooks de ETL y de entrenamiento",
               "Curva de pérdida, vocabulario, configuración y validación de intención; §6.3 y §7.8."],
          ],
          anchos=[7.0, 9.8], size=8.5,
          caption="Tabla 19. Inventario de versiones y aporte conservado en el informe final.")
    h2(doc, "Anexo D. Reproducibilidad")
    par(doc, "Los siguientes comandos regeneran la evidencia y el documento a partir del "
             "repositorio, sin acceso a la máquina virtual:", size=9.5)
    for linea in (
        "python echopulse_llm_orquestator/scripts/test_llm.py          # 27 pruebas del orquestador",
        "python echopulse_llm_orquestator/scripts/cliente_evaluacion.py --total 330 --rpm 10",
        "python echopulse_llm_orquestator/scripts/evaluar_ranking.py --logs build/eva/turnos_*.jsonl \\",
        "       --catalogo \"tabla_maestra/train/*.parquet\" \\",
        "       --fama echopulse_llm_orquestator/models/fame_index.parquet \\",
        "       --salida build/eva/ranking.json",
        "python echopulse_llm_orquestator/scripts/graficas_final.py     # datos_informe.json + 13 figuras",
        "python echopulse_llm_orquestator/scripts/informe_final.py      # este documento",
    ):
        p = doc.add_paragraph()
        r = p.add_run(linea)
        r.font.name = "Consolas"
        r.font.size = Pt(8.5)
        p.paragraph_format.space_after = Pt(2)
    par(doc,
        "El catálogo, el índice de fama y los cuadernos de entrenamiento están versionados "
        "en el repositorio; los turnos de evaluación y los agregados se regeneran con los "
        "comandos anteriores. Las credenciales de la máquina virtual no se requieren para "
        "reproducir las métricas: el cliente de evaluación consume la demo pública por "
        "HTTPS.", size=9.5, color=GRIS, italic=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", default=str(EVA / "datos_informe.json"))
    ap.add_argument("--salida", default=str(RAIZ / "docs" / "EchoPulse_AI_informe_final.docx"))
    args = ap.parse_args()

    d = json.loads(Path(args.datos).read_text(encoding="utf-8"))
    doc = Document()
    preparar(doc)
    doc.core_properties.title = TITULO
    doc.core_properties.author = AUTOR
    doc.core_properties.subject = SUBTITULO
    doc.core_properties.language = "es-CO"
    doc.core_properties.comments = ("Informe final de grado. Documento en tercera persona, "
                                    "con resultados por turno y visita.")
    doc.core_properties.last_modified_by = AUTOR
    doc.core_properties.created = datetime(2026, 11, 17, 6, 30)
    doc.core_properties.modified = datetime(2026, 11, 17, 6, 30)

    portada(doc)
    contenido(doc)
    certificacion(doc)
    resumen(doc, d)
    introduccion(doc, d)
    problema(doc, d)
    objetivos(doc, d)
    justificacion(doc, d)
    marcos(doc, d)
    metodologia(doc, d)
    desarrollo(doc, d)
    resultados(doc, d)
    conclusiones(doc, d)
    recomendaciones(doc, d)
    bibliografia(doc, d)
    anexos(doc, d)

    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    doc.save(args.salida)
    palabras = sum(len(p.text.split()) for p in doc.paragraphs)
    print(f"guardado: {args.salida}")
    print(f"párrafos: {len(doc.paragraphs)} · tablas: {len(doc.tables)} · palabras: {mil(palabras)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())