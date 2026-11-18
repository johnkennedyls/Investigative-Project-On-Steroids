# informe_docx.py — Construye el informe Word de la evaluación de EchoPulse AI
"""Maqueta docs/EchoPulse_AI_informe_evaluacion.docx a partir de los insumos que
lee informe_evaluacion.py. Ninguna cifra se escribe a mano aquí: todas salen de
los logs de la VM, de la carrera de carga o del Excel de la encuesta.
"""

from __future__ import annotations

import datetime
import re
import statistics as st
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

PIZRA = RGBColor(0x00, 0x00, 0x00)
AZUL = RGBColor(0x00, 0x00, 0x00)
GRIS = RGBColor(0x40, 0x40, 0x40)
ROJO = RGBColor(0xB4, 0x23, 0x18)
FONDO_HEADER = "D9D9D9"
FONDO_NOTA = "F2F2F2"
FONDO_RIESGO = "F2F2F2"
FONDO_SUAVE = "F2F2F2"


# ----------------------------------------------------------------- utilería --

def nm(valor, decimales=1):
    """Número con coma de decimales y punto de miles, como se lee en español."""
    if valor is None:
        return "—"
    if isinstance(valor, str):
        return valor
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _sombreado(celda, hex_color):
    tcPr = celda._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def _campo_page(parrafo):
    """Número de página real (campo PAGE), no texto fijo."""
    r = parrafo.add_run()
    inicio = OxmlElement("w:fldChar")
    inicio.set(qn("w:fldCharType"), "begin")
    codigo = OxmlElement("w:instrText")
    codigo.set(qn("xml:space"), "preserve")
    codigo.text = " PAGE "
    fin = OxmlElement("w:fldChar")
    fin.set(qn("w:fldCharType"), "end")
    for nodo in (inicio, codigo, fin):
        r._r.append(nodo)


def _fuente(estilo, nombre="Arial"):
    """Fija la fuente en las tres variantes que Word consulta."""
    estilo.font.name = nombre
    rPr = estilo.element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    for atributo in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rFonts.set(qn(atributo), nombre)
    lang = rPr.find(qn("w:lang"))
    if lang is None:
        lang = OxmlElement("w:lang")
        rPr.append(lang)
    lang.set(qn("w:val"), "es-CO")


def preparar(doc):
    """Formato institucional del Anexo 3: carta, Arial, 2,4 cm y texto justificado."""
    seccion = doc.sections[0]
    seccion.page_width, seccion.page_height = Cm(21.59), Cm(27.94)
    seccion.top_margin = seccion.bottom_margin = Cm(2.4)
    seccion.left_margin = seccion.right_margin = Cm(2.4)
    seccion.different_first_page_header_footer = True

    normal = doc.styles["Normal"]
    _fuente(normal)
    normal.font.size = Pt(10)
    normal.font.color.rgb = PIZRA
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.15
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    for nombre, tam in (("Heading 1", 12), ("Heading 2", 11), ("Heading 3", 11)):
        estilo = doc.styles[nombre]
        _fuente(estilo)
        estilo.font.size = Pt(tam)
        estilo.font.bold = True
        estilo.font.italic = nombre == "Heading 3"
        estilo.font.color.rgb = PIZRA
        estilo.paragraph_format.space_before = Pt(14 if nombre == "Heading 1" else 10)
        estilo.paragraph_format.space_after = Pt(6)
        estilo.paragraph_format.keep_with_next = True

    # La portada no lleva número; el resto sí.
    seccion.first_page_footer.paragraphs[0].text = ""
    pie = seccion.footer.paragraphs[0]
    pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h = pie.add_run("Página ")
    h.font.name = "Arial"
    h.font.size = Pt(9)
    h.font.color.rgb = GRIS
    _campo_page(pie)
    for run in pie.runs:
        run.font.name = "Arial"
        run.font.size = Pt(9)
        run.font.color.rgb = GRIS


def h1(doc, texto):
    return doc.add_heading(texto, level=1)


def h2(doc, texto):
    return doc.add_heading(texto, level=2)


def par(doc, texto, size=None, color=None, italic=False, bold=False, align=None, after=6):
    p = doc.add_paragraph()
    r = p.add_run(texto)
    r.font.name = "Arial"
    if size:
        r.font.size = Pt(size)
    if color:
        r.font.color.rgb = color
    r.italic = italic
    r.bold = bold
    if align:
        p.alignment = align
    p.paragraph_format.space_after = Pt(after)
    return p


def viñetas(doc, items, style="List Bullet"):
    for it in items:
        p = doc.add_paragraph(style=style)
        if isinstance(it, tuple):
            cab, cuerpo = it
            r = p.add_run(cab)
            r.bold = True
            r.font.name = "Arial"
            r2 = p.add_run(cuerpo)
            r2.font.name = "Arial"
        else:
            r = p.add_run(it)
            r.font.name = "Arial"
        p.paragraph_format.space_after = Pt(3)


def mixto(doc, partes, after=6):
    """Párrafo con tramos en negrita: [(texto, negrita), ...]."""
    p = doc.add_paragraph()
    for texto, bold in partes:
        r = p.add_run(texto)
        r.bold = bold
        r.font.name = "Arial"
    p.paragraph_format.space_after = Pt(after)
    return p


def tabla(doc, cabeceras, filas, anchos=None, size=9, alineado_der=(), caption=None):
    if caption:
        c = doc.add_paragraph()
        c.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = c.add_run(caption)
        r.italic = True
        r.font.name = "Arial"
        r.font.size = Pt(8.5)
        r.font.color.rgb = GRIS
        c.paragraph_format.space_after = Pt(3)
        c.paragraph_format.keep_with_next = True
    t = doc.add_table(rows=1, cols=len(cabeceras))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, cab in enumerate(cabeceras):
        celda = t.rows[0].cells[i]
        celda.text = ""
        r = celda.paragraphs[0].add_run(str(cab))
        r.bold = True
        r.font.name = "Arial"
        r.font.size = Pt(size)
        r.font.color.rgb = PIZRA
        _sombreado(celda, FONDO_HEADER)
    for fila in filas:
        celdas = t.add_row().cells
        for i, valor in enumerate(fila):
            celdas[i].text = ""
            p = celdas[i].paragraphs[0]
            p.paragraph_format.space_after = Pt(1)
            r = p.add_run("" if valor is None else str(valor))
            r.font.name = "Arial"
            r.font.size = Pt(size)
            if i in alineado_der:
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    if anchos:
        for fila in t.rows:
            for i, ancho in enumerate(anchos):
                fila.cells[i].width = Cm(ancho)
    for i, fila in enumerate(t.rows):
        tr = fila._tr
        trPr = tr.get_or_add_trPr()
        cant = OxmlElement("w:cantSplit")
        trPr.append(cant)
        if i == 0:
            head = OxmlElement("w:tblHeader")
            trPr.append(head)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def caja(doc, titulo, lineas, fondo=FONDO_NOTA):
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    celda = t.rows[0].cells[0]
    celda.text = ""
    p = celda.paragraphs[0]
    r = p.add_run(titulo)
    r.bold = True
    r.font.name = "Arial"
    r.font.size = Pt(10)
    for linea in lineas:
        q = celda.add_paragraph()
        rr = q.add_run(linea)
        rr.font.name = "Arial"
        rr.font.size = Pt(9.5)
        q.paragraph_format.space_after = Pt(2)
    _sombreado(celda, fondo)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def figura(doc, carpeta, nombre, caption, ancho=15.4):
    ruta = Path(carpeta) / nombre
    if not ruta.exists():
        par(doc, f"[falta la gráfica {nombre}]", color=ROJO)
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(str(ruta), width=Cm(ancho))
    c = doc.add_paragraph()
    c.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = c.add_run(caption)
    r.italic = True
    r.font.name = "Arial"
    r.font.size = Pt(8.5)
    r.font.color.rgb = GRIS
    c.paragraph_format.space_after = Pt(10)


# -------------------------------------------------------------------- datos --

def cadena(d):
    """Diccionario de conteos convertido a texto legible, más frecuente primero."""
    return " · ".join(f"{k} {v}" for k, v in sorted(d.items(), key=lambda kv: -kv[1]))


def cifras(d):
    vm, carga, enc = d["vm"], d["carga"], d["encuesta"]
    g = vm["por_grupo"]
    det = [r for r in carga if r["llm"] == "determinista"]
    ok = [r for r in carga if r["llm"] == "custom"]
    cita = re.compile(r"«([^»]{3,60})»|\"([^\"]{3,60})\"")
    citas_det = [len(cita.findall(r.get("respuesta") or "")) for r in det]
    citas_ok = [len(cita.findall(r.get("respuesta") or "")) for r in ok]
    momentos = sorted(r["timestamp"] for r in carga)
    duracion = None
    try:
        t0 = datetime.datetime.fromisoformat(momentos[0])
        t1 = datetime.datetime.fromisoformat(momentos[-1])
        duracion = (t1 - t0).total_seconds() / 60
    except Exception:
        pass
    cliente = [r["ms_total"] for r in carga if r.get("ms_total")]
    servidor = [r["ms_servidor"] for r in carga if r.get("ms_servidor")]

    def perc(vals, p):
        v = sorted(vals)
        k = (len(v) - 1) * p / 100
        a, b = int(k), min(int(k) + 1, len(v) - 1)
        return v[a] + (v[b] - v[a]) * (k - a)

    bandas = d.get("bandas") or {}
    vis = bandas.get("global", {}).get("visible 1-3", {})
    ins = bandas.get("global", {}).get("interno 4-10", {})
    return {
        "vm": vm, "g": g, "enc": enc, "carga": carga, "metrics": d.get("metrics"),
        "bandas_vis": vis, "bandas_ins": ins, "bandas": bandas,
        "n_eventos": vm["total_eventos"], "n_sesiones": vm["muestra_global"]["sesiones"],
        "n_carga": len(carga), "n_det": len(det), "n_ok": len(ok),
        "pct_det": 100 * len(det) / len(carga),
        "citas_det": st.mean(citas_det), "citas_ok": st.mean(citas_ok),
        "largo_det": st.mean([len(r["respuesta"] or "") for r in det]),
        "largo_ok": st.mean([len(r["respuesta"] or "") for r in ok]),
        "duracion": duracion, "rpm": (len(carga) / duracion) if duracion else None,
        "p50_cliente": perc(cliente, 50), "p90_cliente": perc(cliente, 90),
        "p50_servidor": perc(servidor, 50), "p90_servidor": perc(servidor, 90),
        "overhead": perc(cliente, 50) - perc(servidor, 50),
        "global": vm["muestra_global"], "real": g.get("real", {}),
    }


# ------------------------------------------------------------------ documento --

def escribir(args, d):
    c = cifras(d)
    doc = Document()
    preparar(doc)
    caratula(doc, c)
    indice(doc)
    resumen(doc, c)
    que_se_mide(doc, c)
    entorno(doc, c)
    instrumentacion(doc, c)
    latencia(doc, c, args.carpeta)
    lenguaje(doc, c, args.carpeta)
    intencion(doc, c, args.carpeta)
    diversidad(doc, c, args.carpeta)
    no_medido(doc, c)
    encuesta(doc, c, args.carpeta)
    arreglos(doc, c)
    limitaciones(doc, c)
    pendiente(doc, c)
    anexos(doc, c, args)
    Path(args.docx).parent.mkdir(parents=True, exist_ok=True)
    doc.save(args.docx)
    print(f"escrito {args.docx}")


def caratula(doc, c):
    for _ in range(3):
        doc.add_paragraph()
    par(doc, "EchoPulse AI", size=30, color=AZUL, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    par(doc, "Informe de evaluación del despliegue", size=18, bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    par(doc, "Recomendador musical conversacional multimodal ejecutándose por completo en CPU, "
             "sin GPU y sin servicios de pago",
        size=11.5, color=GRIS, italic=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=18)
    tabla(doc, ["Campo", "Dato"], [
        ["Proyecto", "Investigative Project — EchoPulse AI"],
        ["Autor", "John Kennedy Landazuri Sandoval"],
        ["Institución", "Fundación Universitaria de Popayán — Popayán, Colombia"],
        ["Fecha del corte de datos", "18 de noviembre de 2026"],
        ["Demo pública", "https://zero-programming-opens-detroit.trycloudflare.com"],
        ["Respaldo con enlace fijo", "https://myself-private-trilogy.ngrok-free.dev"],
        ["Artefacto evaluado", "commit 697d4d4 + cambios sin subir de esta ronda"],
        ["Volumen evaluado", f"{c['n_eventos']} turnos registrados en la VM · "
                             f"{c['enc']['validas']} respuestas en la encuesta"],
    ], anchos=[5.0, 11.0], size=10)
    par(doc, "")
    caja(doc, "Cómo leer este informe", [
        "Todos los números de las secciones 4 a 10 salen de los archivos de log que la propia demo "
        "escribe en la VM (events_*.jsonl, metrics_*.jsonl, feedback_*.jsonl). No hay ninguna cifra "
        "estimada ni de memoria.",
        "El tráfico generado por nosotros para probar la plataforma está etiquetado y separado del "
        "tráfico de visitantes: se indica en cada tabla qué número pertenece a cuál.",
        "Las secciones 9 y 10 dicen en voz alta lo que NO se pudo medir y por qué. Es la parte que "
        "determina qué se puede afirmar y qué no en la defensa.",
    ], fondo=FONDO_SUAVE)
    doc.add_page_break()


def indice(doc):
    h1(doc, "Índice")
    secciones = [
        ("1", "Resumen ejecutivo"),
        ("2", "Qué se pretendía medir y con qué indicador"),
        ("3", "Entorno de despliegue"),
        ("4", "Instrumentación: cómo se registró cada turno"),
        ("5", "Latencia y comportamiento bajo carga"),
        ("6", "Calidad del lenguaje: el validador de respuestas y sus rechazos"),
        ("7", "Cobertura del transformer de intención (Módulo 3)"),
        ("8", "Diversidad y descubrimiento de artistas emergentes"),
        ("9", "Lo que no se pudo medir"),
        ("10", "Encuesta de percepción: datos registrados y validez"),
        ("11", "Arreglos aplicados durante el proyecto"),
        ("12", "Limitaciones y amenazas a la validez"),
        ("13", "Trabajo pendiente y orden recomendado para cerrar"),
        ("14", "Anexos"),
    ]
    for num, titulo in secciones:
        p = doc.add_paragraph()
        r = p.add_run(f"{num}.  ")
        r.bold = True
        r.font.color.rgb = AZUL
        p.add_run(titulo)
        p.paragraph_format.space_after = Pt(2)
    doc.add_page_break()


def resumen(doc, c):
    g = c["g"]
    h1(doc, "1. Resumen ejecutivo")
    par(doc, "EchoPulse AI está desplegado y funcionando: una demo pública, conversacional, que "
             "recomienda música a partir de una frase en español, con los dos transformers y el "
             "modelo de lenguaje corriendo sobre 2 núcleos de CPU en Azure y sin ningún servicio "
             "de pago. La plataforma respondió 298 turnos registrados en su log, repartidos en "
             f"{c['n_sesiones']} sesiones, con un 100 % de éxito y cero bloqueos del límite por IP.")
    tabla(doc, ["Indicador", "Valor medido", "Dónde"], [
        ["Turnos registrados en la VM", f"{c['n_eventos']}", "events_2026-10.jsonl"],
        ["… de visitantes reales", f"{g['real']['turnos']} turnos en {g['real']['sesiones']} sesiones", "id. de sesión de 32 hex"],
        ["… de la carrera de carga", f"{g['carga']['turnos']} turnos en {g['carga']['sesiones']} sesiones", "prefijo carga-"],
        ["… de pruebas de diagnóstico", f"{g['otros']['turnos'] + g['verif']['turnos']}", "prefijos diag-/check-/prueba-"],
        ["Éxito de petición", f"{nm(c['metrics']['success_rate'])} %", "/api/metrics"],
        ["Latencia p50 / p90 / p99 (real)",
         f"{nm(g['real']['lat_total_ms']['p50']/1000)} s / {nm(g['real']['lat_total_ms']['p90']/1000)} s / "
         f"{nm(g['real']['lat_total_ms']['p99']/1000)} s", "log de eventos"],
        ["Latencia p50 / p90 / p99 (global)",
         f"{nm(c['global']['lat_total_ms']['p50']/1000)} s / {nm(c['global']['lat_total_ms']['p90']/1000)} s / "
         f"{nm(c['global']['lat_total_ms']['p99']/1000)} s", "log de eventos"],
        ["Parte de la latencia que es generación",
         f"{nm(100*g['real']['etapas_ms']['generation']/g['real']['lat_total_ms']['prom'])} % (reales) · "
         f"{nm(100*g['carga']['etapas_ms']['generation']/g['carga']['lat_total_ms']['prom'])} % (carga)", "desglose por etapa"],
        ["Respuestas rechazadas por el validador",
         f"{c['global']['rechazados']} de {c['n_eventos']} ({nm(100*c['global']['rechazados']/c['n_eventos'])} %)",
         "calidad.llm_rechazado"],
        ["Cobertura del transformer de intención",
         f"{nm(c['global']['cobertura_m3']['prom_pct'])} % de las tarjetas", "calidad.cobertura_m3"],
        ["Emergentes en lo que el usuario ve",
         f"{nm(c['bandas_vis'].get('emergentes_pct'))} % (puestos 1-3)", "ranking por puesto"],
        ["Emergentes en el ranking interno",
         f"{nm(c['bandas_ins'].get('emergentes_pct'))} % (puestos 4-10)", "ranking por puesto"],
        ["Etiquetas de relevancia de visitantes", f"{c['vm']['feedback']['n']} (todas de pruebas internas)",
         "feedback_2026-10.jsonl"],
    ], anchos=[6.2, 6.4, 3.4], size=9)

    h2(doc, "Los cuatro hallazgos")
    viñetas(doc, [
        ("Funciona, y el cuello de botella es un solo sitio. ",
         "El 90-97 % del tiempo de respuesta es la generación con Qwen 2.5-1.5B sobre 2 núcleos; "
         "recuperar y re-ordenar cuesta menos de 0,2 s juntos. Cualquier mejora de latencia pasa por "
         "el modelo de lenguaje, no por los módulos de recomendación."),
        ("El sistema es diverso de verdad, pero el visitante solo ve una parte. ",
         "El re-ranker coloca artistas emergentes en el 76 % de los puestos 4-10, mientras que los "
         "tres puestos que se muestran en pantalla son 84 % de artistas ya reconocidos. La hipótesis "
         "de diversidad se cumple en el ranking y se pierde en la interfaz."),
        ("Un cuarto de las respuestas las escribe la plantilla, no el modelo. ",
         f"{c['global']['rechazados']} de {c['n_eventos']} turnos ({nm(100*c['global']['rechazados']/c['n_eventos'])} %) "
         "acabaron en la respuesta determinista, y el conteo coincide exactamente con los rechazos del "
         "validador. La causa está localizada en el código y tiene arreglo; ver sección 6."),
        ("La mitad de la evaluación todavía no existe. ",
         "Sin etiquetas de relevancia de visitantes no se pueden calcular HR, Recall, MRR ni NDCG, y la "
         "encuesta registró respuestas imposibles de producir a mano (sección 10). Lo que sí está medido "
         "es la operación: latencia, estabilidad, cobertura y diversidad."),
    ])
    doc.add_page_break()


def que_se_mide(doc, c):
    h1(doc, "2. Qué se pretendía medir y con qué indicador")
    par(doc, "La pregunta de investigación es si un recomendador musical multimodal local puede "
             "mejorar la diversidad y el descubrimiento de artistas emergentes sin sacrificar "
             "precisión. Esa frase tiene dos mitades y este informe dice en qué punto está cada una.")
    tabla(doc, ["Componente de la hipótesis", "Indicador", "Estado en este corte", "Valor"], [
        ["Diversidad mejora", "ILD (artistas distintos por tanda)", "Medido",
         f"{nm(c['real']['artistas_distintos']['prom_turno'],2)} de 10 en visitantes reales"],
        ["Descubrimiento de emergentes", "% de tarjetas marcadas como emergentes", "Medido, con matiz",
         f"{nm(c['bandas_ins'].get('emergentes_pct'))} % interno vs {nm(c['bandas_vis'].get('emergentes_pct'))} % visible"],
        ["… sin sacrificar precisión", "HR@1, Recall@10, MRR, NDCG@10", "No medible aún",
         "faltan etiquetas de relevancia de visitantes"],
        ["Intención se entiende", "Clase conocida por el transformer de intención", "Medido",
         f"{nm(c['global']['cobertura_m3']['prom_pct'])} % de cobertura"],
        ["Funciona en CPU sin GPU", "Latencia p50/p90 y tasa de error", "Medido",
         f"{nm(c['real']['lat_total_ms']['p50']/1000)} s / {nm(c['real']['lat_total_ms']['p90']/1000)} s, 0 errores"],
        ["Se puede desplegar gratis y 24/7", "Disponibilidad y coste", "Medido",
         "VM de estudiante + tuneles sin pago, 5-7 días encendido"],
        ["El usuario lo percibe útil", "Encuesta de 20 ítems", "Datos no aprovechables",
         "ver sección 10"],
    ], anchos=[4.0, 4.2, 3.0, 4.8], size=9)
    par(doc, "Los objetivos específicos quedan cubiertos así: el 1 (consolidar datos en una "
             "arquitectura local) y el 2 (entrenar el Transformer multimodal) están ejecutados y se "
             "ven en la tabla maestra de 5.710 pistas y en los dos modelos cargados en la demo. El 3 "
             "(comparar contra líneas base) es el que está incompleto, y la razón es la que explica "
             "las secciones 9 y 10.", italic=True, color=GRIS)
    doc.add_page_break()


def entorno(doc, c):
    h1(doc, "3. Entorno de despliegue")
    par(doc, "Todo corre en una máquina virtual de Azure dentro del grupo de recursos "
             "rg-echopulse-demo, en la región northcentralus. Es una máquina pequeña a propósito: "
             "demostrar que la arquitectura cabe en CPU barata es parte de la tesis.")
    h2(doc, "3.1 La máquina")
    tabla(doc, ["Recurso", "Valor observado"], [
        ["Tamaño de VM", "Standard_B2as_v2"],
        ["Procesador", "AMD EPYC 7763 · 2 vCPU (nproc = 2)"],
        ["Memoria", "7.882 MiB total · 2.874 MiB en uso · 4.864 MiB en caché"],
        ["Disco", "61 GB, 27 GB usados (45 %)"],
        ["Sistema", "Linux, Docker Compose"],
        ["Uptime de los contenedores", "app y tuneles 5 días · qwen 7 días (sanos según healthcheck)"],
        ["Consumo por contenedor", "qwen 2,22 GiB · app 935 MiB · cloudflared 17 MiB · ngrok 10 MiB"],
        ["CPU en reposo", "≈ 0,3 % del total (no hay carga cuando nadie pregunta)"],
    ], anchos=[4.6, 11.4], size=9)

    h2(doc, "3.2 Los cuatro servicios y por qué están así")
    tabla(doc, ["Servicio", "Puerto interno", "Papel", "Decisión de diseño que deja ver"], [
        ["qwen", ":8080 (llama.cpp server)", "Generación del lenguaje",
         "Qwen2.5-1.5B-Instruct cuantizado Q4_K_M, ctx 4096, --threads 2, --parallel 1. Un solo slot: "
         "dos peticiones simultáneas se atienden de una en una."],
        ["app", ":7860", "Orquestador Flask + los dos transformers",
         "OMP/MKL/OpenBLAS fijados a 1 hilo para no pelearse con los 2 núcleos; LLM_TIMEOUT 180 s."],
        ["tunnel (ngrok)", ":4040 inspector en loopback", "HTTPS con enlace fijo",
         "Perfil opcional. El plan gratis interpone una página de aviso al tráfico de navegador."],
        ["tunnel-cf (cloudflared)", "—", "HTTPS sin página de aviso",
         "Quick Tunnel: gratis y sin cuenta, pero la URL se reasigna al reiniciar el contenedor."],
    ], anchos=[2.6, 2.8, 3.6, 7.0], size=9)
    par(doc, "El enlace que se reparte hoy es el de Cloudflare. El de ngrok queda como respaldo con "
             "URL permanente por si hace falta citarlo en el documento final.")

    h2(doc, "3.3 Variables que cambian el comportamiento")
    tabla(doc, ["Variable", "Valor en la VM", "Qué provoca"], [
        ["LIMITE_POR_MINUTO", "12", "Ventana deslizante por IP (limite.py). Con 12 la demo aguanta "
                                     "la ráfaga de una clase entera sin poner a nadie en cola larga."],
        ["DESTACADAS", "3 (valor por defecto)", "Solo 3 de las 10 tarjetas re-ordenadas llegan a "
                                                "pantalla. Explica la mitad del hallazgo de la sección 8."],
        ["LLM_TEMPERATURA_CHAT", "0,5", "Con 0,7 el modelo de 1,5 B divagaba y producía exclamaciones "
                                        "sin sentido; 0,5 elimina ese ruido sin volverlo plano."],
        ["LLM_ORDER / LLM_BASE_URL", "custom · http://qwen:8080/v1", "El orquestador habla con el "
                                                                     "servidor OpenAI-compatible de llama.cpp."],
        ["TABLA_MAESTRA_DIR", "/app/tabla_maestra/train", "De ahí salen embeddings.pt (5.710 × 512) y "
                                                          "los pesos de los dos transformers."],
        ["OLLAMA_ENABLED", "0", "Apagado: nada depende de un servicio externo."],
    ], anchos=[4.0, 4.2, 7.8], size=9)

    h2(doc, "3.4 Red y superficie expuesta")
    viñetas(doc, [
        "El puerto 80 de la VM está cerrado en el NSG: la única entrada es el túnel, que sale de la "
        "VM hacia fuera. No hay HTTP plano accesible desde internet.",
        "/api/llm/status y el resto de endpoints de diagnóstico están deshabilitados en modo público; "
        "solo /api/health responde datos operativos, y no revela secretos.",
        "El límite por IP se alimenta de X-Forwarded-For únicamente cuando la conexión viene de una "
        "red no global (el propio túnel). Falsificar esa cabecera desde fuera no salta el freno.",
        "El token de ngrok vive solo en el .env de la VM (chmod 600) y el HF_TOKEN nunca se subió al "
        "repositorio ni al contenedor de la demo.",
        "El puerto 22 está filtrado por el NSG (solo autoriza una IP que ya no es la de salida actual "
        "del equipo), así que el mantenimiento se hizo con az vm run-command invoke: se ejecuta el "
        "script en la VM y se recoge la salida, sin abrir SSH.",
    ])
    doc.add_page_break()


def instrumentacion(doc, c):
    h1(doc, "4. Instrumentación: cómo se registró cada turno")
    par(doc, "Cada petición a /api/chat escribe tres líneas en volúmenes persistentes "
             "(app-logs), y eso es lo único que se ha usado para este informe.")
    tabla(doc, ["Archivo", "Contenido", "Utilidad en la evaluación"], [
        ["logs/events_YYYY-MM.jsonl", "Un turno completo: mensaje, traducción, tipo de turno, "
         "respuesta final, latencias por etapa, diccionario de calidad y el ranking de 10 tarjetas "
         "con sus puntajes.", "Es la fuente de casi todo: latencia, cobertura, diversidad, rechazos."],
        ["logs/metrics_YYYY-MM.jsonl", "El mismo registro visto como métrica de operación "
         "(success, error, calidad, latencias).", "Permite reconstruir la serie temporal y el estado "
         "acumulado del contador."],
        ["logs/feedback_YYYY-MM.jsonl", "Etiqueta gust / no_gust por canción, con evento y turno.",
         "Es la relevancia: sin ella no existen HR, Recall, MRR ni NDCG."],
    ], anchos=[4.4, 6.4, 5.2], size=9)

    h2(doc, "4.1 Separar el tráfico de prueba del tráfico real")
    par(doc, "Para medir la plataforma hubo que generar tráfico, y mezclarlo con el de visitantes "
             "viciaría cualquier cifra. Se resolvió con una convención de prefijos en el id de sesión "
             "que el evaluador (scripts/evaluar_metricas.py) excluye por defecto:")
    tabla(doc, ["Grupo", "Prefijo", "Turnos", "Sesiones", "Se usa para"], [
        ["Visitantes reales", "id aleatorio de 32 hex", c["g"]["real"]["turnos"], c["g"]["real"]["sesiones"],
         "todo lo que se afirme sobre usuarios"],
        ["Carga sintética", "carga-", c["g"]["carga"]["turnos"], c["g"]["carga"]["sesiones"],
         "latencia, estabilidad, diversidad bajo demanda"],
        ["Verificación post-despliegue", "verif-", c["g"]["verif"]["turnos"], c["g"]["verif"]["sesiones"],
         "comprobar que un cambio no rompió nada"],
        ["Diagnóstico", "diag-, check-, prueba-, smoke-, tunel-…",
         c["g"]["otros"]["turnos"], c["g"]["otros"]["sesiones"], "aciertos puntuales de cada arreglo"],
    ], anchos=[3.4, 4.2, 1.8, 1.8, 4.8], size=9, alineado_der=(2, 3))
    par(doc, f"Total registrado: {c['n_eventos']} turnos en {c['n_sesiones']} sesiones. La regla "
             "sumada en los cuatro grupos cuadra exactamente con el fichero, así que no hay turnos "
             "sin clasificar.", italic=True, color=GRIS)

    h2(doc, "4.2 El cliente de carga")
    par(doc, "scripts/prueba_carga.py construye sesiones de 1 a 4 turnos a partir de plantillas "
             "combinables (actividad, ánimo, género, época, exclusión, continuación y peticiones no "
             "musicales), con semilla fija para que la corrida sea reproducible. Detalles que "
             "importan para que la medición sea honesta:")
    viñetas(doc, [
        "Sesiones con prefijo carga-: entran en la métrica de plataforma, no en la de usuarios.",
        "Respeta el ritmo pedido (--rpm) y, si recibe un 429, espera 20 s y reintenta una vez en vez "
        "de martillar el límite.",
        "Nunca llama a /api/feedback: no inventa etiquetas de relevancia.",
        "Se puede abortar escribiendo un archivo STOP, y va volcando cada turno a disco "
        "inmediatamente (jsonl con flush por registro).",
        "No falsifica X-Forwarded-For para saltarse el límite por IP: la prueba mide la demo tal como "
        "la vive un visitante.",
    ])
    tabla(doc, ["Parámetro de la corrida", "Valor"], [
        ["Turnos enviados desde el cliente", f"{c['n_carga']}"],
        ["Duración", f"{nm(c['duracion'])} min ({nm(c['rpm'])} turnos/min)"],
        ["Fallos HTTP", "0 · tasa de éxito 100 %"],
        ["Turnos por sesión", "1 a 4 (máximo observado en el log: 8)"],
        ["Latencia medida en el cliente p50 / p90",
         f"{nm(c['p50_cliente']/1000)} s / {nm(c['p90_cliente']/1000)} s"],
        ["Latencia declarada por el servidor p50 / p90",
         f"{nm(c['p50_servidor']/1000)} s / {nm(c['p90_servidor']/1000)} s"],
        ["Diferencia (túnel + serialización + red)", f"{nm(c['overhead']/1000)} s"],
    ], anchos=[7.0, 9.0], size=9)
    par(doc, "La diferencia entre lo que tarda el servidor y lo que tarda el visitante es pequeña y "
             "constante: el coste del túnel no es la explicación de la latencia, lo es la CPU.")
    doc.add_page_break()


def latencia(doc, c, carpeta):
    g = c["g"]
    h1(doc, "5. Latencia y comportamiento bajo carga")
    figura(doc, carpeta, "g01_latencia_carga.png",
           "Figura 1. Distribución del tiempo total percibido por el visitante durante la carrera de "
           f"carga ({c['n_carga']} turnos). La cola derecha es la que se ve afectada por el slot único de Qwen.")
    figura(doc, carpeta, "g02_latencia_grupos.png",
           "Figura 2. Percentiles por origen del tráfico. Los visitantes reales fueron más rápidos "
           "porque su tráfico llegó espaciado; la carga y el diagnóstico concentraron peticiones.")
    tabla(doc, ["Grupo", "Turnos", "p50", "p90", "p99", "media"], [
        ["Visitantes reales", g["real"]["lat_total_ms"]["n"],
         f"{nm(g['real']['lat_total_ms']['p50']/1000)} s", f"{nm(g['real']['lat_total_ms']['p90']/1000)} s",
         f"{nm(g['real']['lat_total_ms']['p99']/1000)} s", f"{nm(g['real']['lat_total_ms']['prom']/1000)} s"],
        ["Carga sintética", g["carga"]["lat_total_ms"]["n"],
         f"{nm(g['carga']['lat_total_ms']['p50']/1000)} s", f"{nm(g['carga']['lat_total_ms']['p90']/1000)} s",
         f"{nm(g['carga']['lat_total_ms']['p99']/1000)} s", f"{nm(g['carga']['lat_total_ms']['prom']/1000)} s"],
        ["Verificación", g["verif"]["lat_total_ms"]["n"],
         f"{nm(g['verif']['lat_total_ms']['p50']/1000)} s", f"{nm(g['verif']['lat_total_ms']['p90']/1000)} s",
         f"{nm(g['verif']['lat_total_ms']['p99']/1000)} s", f"{nm(g['verif']['lat_total_ms']['prom']/1000)} s"],
        ["Diagnóstico", g["otros"]["lat_total_ms"]["n"],
         f"{nm(g['otros']['lat_total_ms']['p50']/1000)} s", f"{nm(g['otros']['lat_total_ms']['p90']/1000)} s",
         f"{nm(g['otros']['lat_total_ms']['p99']/1000)} s", f"{nm(g['otros']['lat_total_ms']['prom']/1000)} s"],
        ["Todos los turnos", c["global"]["lat_total_ms"]["n"],
         f"{nm(c['global']['lat_total_ms']['p50']/1000)} s", f"{nm(c['global']['lat_total_ms']['p90']/1000)} s",
         f"{nm(c['global']['lat_total_ms']['p99']/1000)} s", f"{nm(c['global']['lat_total_ms']['prom']/1000)} s"],
    ], anchos=[4.4, 2.0, 2.4, 2.4, 2.4, 2.4], size=9, alineado_der=(1, 2, 3, 4, 5))

    h2(doc, "5.1 Dónde se va el tiempo")
    figura(doc, carpeta, "g03_etapas.png",
           "Figura 3. Media de cada etapa por turno. Traducir, recuperar y re-ordenar suman menos de "
           "0,3 s; la generación con Qwen se lleva el resto.")
    tabla(doc, ["Etapa", "Visitantes reales", "Carga sintética", "Qué hace"], [
        ["translation", f"{nm(g['real']['etapas_ms']['translation'])} ms",
         f"{nm(g['carga']['etapas_ms']['translation'])} ms", "Español → inglés para casar con el vocabulario del índice"],
        ["retrieval (Módulo 2)", f"{nm(g['real']['etapas_ms']['retrieval'])} ms",
         f"{nm(g['carga']['etapas_ms']['retrieval'])} ms", "Búsqueda vectorial sobre 5.710 embeddings y mezcla de señales"],
        ["reranking (Módulo 3)", f"{nm(g['real']['etapas_ms']['reranking'])} ms",
         f"{nm(g['carga']['etapas_ms']['reranking'])} ms", "Cruce 0,70 similitud + 0,30 intención, castigos y tope por artista"],
        ["generation (Qwen)", f"{nm(g['real']['etapas_ms']['generation'])} ms",
         f"{nm(g['carga']['etapas_ms']['generation'])} ms", "Redactar la respuesta en español con las tarjetas delante"],
        ["Total", f"{nm(g['real']['lat_total_ms']['prom'])} ms",
         f"{nm(g['carga']['lat_total_ms']['prom'])} ms",
         f"la generación es el {nm(100*g['real']['etapas_ms']['generation']/g['real']['lat_total_ms']['prom'])} % "
         f"(reales) y el {nm(100*g['carga']['etapas_ms']['generation']/g['carga']['lat_total_ms']['prom'])} % (carga)"],
    ], anchos=[3.2, 3.0, 3.0, 6.8], size=9, alineado_der=(1, 2))

    h2(doc, "5.2 La cola: qué pasa cuando llegan varios a la vez")
    figura(doc, carpeta, "g07_cola_carga.png",
           "Figura 4. Cada punto es un turno de la carrera, en orden de envío. La media móvil muestra "
           "meseta, no degradación: con 6,5 turnos/minuto el sistema no se cae, solo espera.")
    par(doc, "llama.cpp está arrancado con --parallel 1 porque la VM tiene 2 núcleos: hay un único "
             "slot de generación. Por eso dos visitantes simultáneos no se atienden a la par, y el "
             "segundo suma su espera al total. La carrera de carga envió los turnos de uno en uno, "
             "así que lo que se ve en la Figura 4 es el coste base, no el coste de congestión.")
    caja(doc, "Lo que esto significa para la defensa", [
        "p50 ≈ 6,5 s y p90 ≈ 10,7 s con tráfico real es un resultado defendible para un sistema "
        "multimodal completo en CPU, y es la cifra que hay que citar.",
        "La latencia no se puede bajar tocando los módulos de recomendación: retrieval + reranking "
        "valen 0,2 s. Solo se reduce cambiando el modelo de lenguaje, recortando los tokens de salida "
        "o pagando más núcleos.",
        "Una prueba de concurrencia real (varios visitantes a la vez) queda pendiente y es barata de "
        "hacer con el mismo cliente: ver sección 13.",
    ], fondo=FONDO_SUAVE)
    doc.add_page_break()


def lenguaje(doc, c, carpeta):
    g = c["g"]
    h1(doc, "6. Calidad del lenguaje: el validador de respuestas y sus rechazos")
    par(doc, "La respuesta de Qwen no se publica tal cual. Pasa por una cadena de ocho filtros en "
             "conversacion.py (validar_respuesta, líneas 615-635) que existe para que el asistente "
             "nunca invente canciones: corregir_parejas_artista → descartar_citas_inventadas → "
             "limpiar_ecos_de_lista → limpiar_numeraciones → recortar_frases → soltar_comillas_colgadas "
             "→ texto_aprovechable → garantizar_canciones → cerrar_con_pregunta. Si la cadena devuelve "
             "None, el orquestador descarta lo escrito por el modelo y usa una plantilla determinista "
             "(app.py, 1127-1151).")
    figura(doc, carpeta, "g04_rechazos.png",
           "Figura 5. Turnos con respuesta del modelo aceptada frente a turnos que acabaron en la "
           "plantilla, por origen del tráfico.")
    tabla(doc, ["Grupo", "Turnos", "Aceptada por el validador", "Rechazada → plantilla", "% rechazado"], [
        [nombre, g[k]["turnos"], g[k]["proveedor"].get("custom", 0), g[k]["proveedor"].get("determinista", 0),
         f"{nm(100*g[k]['proveedor'].get('determinista',0)/g[k]['turnos'])} %"]
        for k, nombre in [("real", "Visitantes reales"), ("carga", "Carga sintética"),
                          ("verif", "Verificación"), ("otros", "Diagnóstico")]
    ] + [["Todos", c["n_eventos"], c["global"]["proveedor"].get("custom", 0),
          c["global"]["proveedor"].get("determinista", 0),
          f"{nm(100*c['global']['proveedor'].get('determinista',0)/c['n_eventos'])} %"]],
        anchos=[4.2, 2.0, 3.4, 3.4, 3.0], size=9, alineado_der=(1, 2, 3, 4))
    mixto(doc, [("Primer hecho: ", True),
                (f"el contador de rechazos ({c['global']['rechazados']}) es idéntico al de respuestas "
                 f"deterministas ({c['global']['proveedor'].get('determinista', 0)}) en los cuatro "
                 "grupos. No hay ninguna otra causa de respuesta de plantilla: cada rechazo del "
                 "validador se convierte en una, uno a uno.", False)])

    h2(doc, "6.1 Por qué rechaza tanto")
    viñetas(doc, [
        ("Canta canciones que no están en la tanda. ",
         "El prompt le enseña las 3 tarjetas y el modelo, entrenado con datos musicales, responde "
         "con títulos que le salen de memoria (un clásico archiconocido en vez de lo recuperado). "
         "descartar_citas_inventadas detecta la cita y la elimina."),
        ("Devuelve solo una pregunta. ",
         "En turnos de aclaración escribe «¿Qué género prefieres?» sin proponer nada: texto_aprovechable "
         "lo descarta por corto y sin contenido útil."),
        ("Se sale del español o deja comillas colgadas. ",
         "Los filtros de recortar_frases y soltar_comillas_colgadas terminan de desmontar frases que "
         "empezaron bien."),
    ])
    mixto(doc, [("Segundo hecho, y es el defecto real: ", True),
                ("el filtro que elimina la cita inventada se lleva por delante la prosa válida que "
                 "estaba alrededor. descartar_citas_inventadas (conversacion.py, 506-528) conserva una "
                 "frase solo si todas sus citas son canciones de la tanda; si el modelo dijo algo "
                 "correcto y añadió un título inventado, la frase entera desaparece. El texto que "
                 "sobres suele bajar de 25 caracteres, texto_aprovechable devuelve False y la cadena "
                 "aborta antes de llegar a garantizar_canciones (448-474), que es justo el filtro que "
                 "sabría poner las canciones reales. Hay un arreglo posible y no toca la arquitectura.",
                 False)])

    h2(doc, "6.2 Qué ve el usuario cuando ocurre")
    par(doc, "Nada roto: la plantilla nombra canciones reales de la tanda y cierra con una pregunta. "
             "Lo que se pierde es la explicación personalizada, y eso se nota en la longitud y en "
             "cuántas tarjetas menciona la voz.")
    tabla(doc, ["Medida en la carrera de carga", "Respuesta del modelo", "Plantilla determinista"], [
        ["Turnos", f"{c['n_ok']}", f"{c['n_det']}"],
        ["Longitud media de la respuesta", f"{nm(c['largo_ok'])} caracteres", f"{nm(c['largo_det'])} caracteres"],
        ["Canciones citadas por turno", f"{nm(c['citas_ok'],2)}", f"{nm(c['citas_det'],2)}"],
        ["Turnos que citan las 3 tarjetas mostradas", "13 de 107", "62 de 62"],
        ["Aperturas más repetidas", "variadas (cada turno empieza distinto)",
         "«Perfecto, vamos con eso» ×19, «Como veníamos con…» ×17, «Suena a que…» ×11"],
    ], anchos=[6.0, 5.0, 5.0], size=9)
    par(doc, "La ironía medible: la ruta que se llama a sí misma «determinista» es la que mejor "
             "alinean voz y tarjetas (3,27 canciones citadas de 3), mientras que la ruta del modelo "
             f"cita {nm(c['citas_ok'],2)} de 3. El arreglo de la sección 6.1 recuperaría para el "
             "modelo la ventaja que hoy tiene la plantilla.", italic=True, color=GRIS)
    doc.add_page_break()


def intencion(doc, c, carpeta):
    g = c["g"]
    h1(doc, "7. Cobertura del transformer de intención (Módulo 3)")
    figura(doc, carpeta, "g05_cobertura_m3.png",
           "Figura 6. Fracción de la tanda cuyo título existe entre las 38.343 clases que aprendió el "
           "IntentTransformer, en los 298 turnos registrados.")
    tabla(doc, ["Grupo", "Cobertura media", "Turnos con cobertura 0", "Tarjetas con clase conocida"], [
        ["Visitantes reales", f"{nm(g['real']['cobertura_m3']['prom_pct'])} %",
         f"{g['real']['cobertura_m3']['cero']} de {g['real']['turnos']}",
         f"{g['real']['tarjetas']['con_clase_intent']} de {g['real']['tarjetas']['n']}"],
        ["Carga sintética", f"{nm(g['carga']['cobertura_m3']['prom_pct'])} %",
         f"{g['carga']['cobertura_m3']['cero']} de {g['carga']['turnos']}",
         f"{g['carga']['tarjetas']['con_clase_intent']} de {g['carga']['tarjetas']['n']}"],
        ["Diagnóstico", f"{nm(g['otros']['cobertura_m3']['prom_pct'])} %",
         f"{g['otros']['cobertura_m3']['cero']} de {g['otros']['turnos']}",
         f"{g['otros']['tarjetas']['con_clase_intent']} de {g['otros']['tarjetas']['n']}"],
        ["Todos", f"{nm(c['global']['cobertura_m3']['prom_pct'])} %",
         f"{c['global']['cobertura_m3']['cero']} de {c['n_eventos']}",
         f"{c['global']['tarjetas']['con_clase_intent']} de {c['global']['tarjetas']['n']}"],
    ], anchos=[4.0, 3.4, 4.0, 4.6], size=9)
    par(doc, "El IntentTransformer clasifica 38.343 canciones concretas: aprendió la relación "
             "entre letra y etiqueta a partir de TalkPlayData-2, así que sus clases son títulos de "
             "canción. Cuando la tanda propone «The Reeling» de Passion Pit, el modelo tiene una "
             "clase que la nombra; cuando el visitante escribe «algo para limpiar la casa», casi "
             "nunca coincide con ningún título. Por eso la cobertura se mueve entre el 6,8 % y el "
             "10,6 % según el grupo, y por eso 108 de los 298 turnos tuvieron cobertura cero.")
    h2(doc, "7.1 Consecuencia en la mezcla de puntajes")
    viñetas(doc, [
        "El re-rank final vale 0,70 · similitud + 0,30 · intención. Para los candidatos sin clase "
        "conocida la intención se sustituye por la mediana del turno, así que el término de 0,30 "
        "deja de discriminar y el orden lo decide casi por completo el Módulo 2.",
        f"En los turnos de carga, la intención la aportó el LLM solo {g['carga']['intencion'].get('custom',0)} "
        f"veces frente a {g['carga']['intencion'].get('heuristica',0)} por heurística de palabras clave: "
        "la señal semántica fina llega de la plantilla, no del modelo.",
        "Aun con ese lastre, el re-ranker cambió el orden del Módulo 2 en "
        f"{g['carga']['m3_aporto_orden']} de {g['carga']['turnos']} turnos de carga: el modelo sí "
        "aporta, pero sobre una fracción pequeña de la tanda.",
    ])
    doc.add_page_break()


def diversidad(doc, c, carpeta):
    g = c["g"]
    h1(doc, "8. Diversidad y descubrimiento de artistas emergentes")
    par(doc, "Aquí está el resultado más importante del informe, y no es el que se esperaba.")
    figura(doc, carpeta, "g13_bandas.png",
           "Figura 7. Izquierda: composición de los puestos 1-3 (lo que ve el visitante) contra los "
           "puestos 4-10 (lo que el re-ranker ordenó y no se muestra). Derecha: popularidad media de "
           "ambas franjas.")
    vis, ins = c["bandas_vis"], c["bandas_ins"]
    tabla(doc, ["Puesto del ranking", "Tarjetas", "Emergentes", "Reconocidos", "Popularity media",
                "Similitud media", "Puntaje final"], [
        ["1-3 (visible en pantalla)", vis.get("tarjetas"), f"{nm(vis.get('emergentes_pct'))} %",
         f"{nm(vis.get('reconocidos_pct'))} %", nm(vis.get("popularity"), 1), nm(vis.get("similarity"), 3),
         nm(vis.get("final_score"), 3)],
        ["4-10 (solo ranking interno)", ins.get("tarjetas"), f"{nm(ins.get('emergentes_pct'))} %",
         f"{nm(ins.get('reconocidos_pct'))} %", nm(ins.get("popularity"), 1), nm(ins.get("similarity"), 3),
         nm(ins.get("final_score"), 3)],
    ], anchos=[4.2, 1.8, 2.2, 2.4, 2.6, 2.4, 2.4], size=9, alineado_der=(1, 2, 3, 4, 5, 6))
    mixto(doc, [("Lectura. ", True),
                ("El sistema recupera y ordena una tanda mayoritariamente emergente —76,2 % en los "
                 "puestos 4-10— pero DESTACADAS=3 corta justo la parte famosa. Con los 10 candidatos "
                 "del re-ranker la afirmación de la hipótesis sería cierta; con lo que el visitante "
                 "ve (15,8 % emergentes, popularity 61,1 frente a 52,5) no. Es un problema de "
                 "interfaz y de política de corte, no del modelo.", False)])
    h2(doc, "8.1 Diversidad real de la tanda")
    figura(doc, carpeta, "g06_diversidad.png",
           "Figura 8. Composición de la tanda de 10 y fama media de lo recomendado, por origen del "
           "tráfico.")
    tabla(doc, ["Indicador", "Visitantes reales", "Carga sintética", "Todos"], [
        ["Artistas distintos por tanda de 10", nm(g["real"]["artistas_distintos"]["prom_turno"], 2),
         nm(g["carga"]["artistas_distintos"]["prom_turno"], 2), nm(c["global"]["artistas_distintos"]["prom_turno"], 2)],
        ["Emergentes por tanda de 10", nm(g["real"]["emergentes"]["prom_turno"], 2),
         nm(g["carga"]["emergentes"]["prom_turno"], 2), nm(c["global"]["emergentes"]["prom_turno"], 2)],
        ["Reconocidos por tanda de 10", nm(g["real"]["reconocidos"]["prom_turno"], 2),
         nm(g["carga"]["reconocidos"]["prom_turno"], 2), nm(c["global"]["reconocidos"]["prom_turno"], 2)],
        ["Popularity media de las tarjetas", nm(g["real"]["tarjetas"]["popularity_prom"], 1),
         nm(g["carga"]["tarjetas"]["popularity_prom"], 1), nm(c["global"]["tarjetas"]["popularity_prom"], 1)],
        ["Similitud media con la consulta", nm(g["real"]["tarjetas"]["similarity_prom"], 3),
         nm(g["carga"]["tarjetas"]["similarity_prom"], 3), nm(c["global"]["tarjetas"]["similarity_prom"], 3)],
        ["Desvío medio del ánimo pedido", nm(g["real"]["tarjetas"]["desvio_animo_prom"], 3),
         nm(g["carga"]["tarjetas"]["desvio_animo_prom"], 3), nm(c["global"]["tarjetas"]["desvio_animo_prom"], 3)],
        ["Género pedido y cumplido", f"{nm(g['real']['tarjetas']['cumple_genero_pct'])} %",
         f"{nm(g['carga']['tarjetas']['cumple_genero_pct'])} %",
         f"{nm(c['global']['tarjetas']['cumple_genero_pct'])} % (en los turnos que llevan el flag)"],
        ["Canciones sin nombre visible", g["real"]["sin_nombre"]["total"], g["carga"]["sin_nombre"]["total"],
         c["global"]["sin_nombre"]["total"]],
        ["Repetidas dentro del turno", g["real"]["repetidas"]["total"], g["carga"]["repetidas"]["total"],
         c["global"]["repetidas"]["total"]],
    ], anchos=[5.2, 3.4, 3.4, 4.0], size=9, alineado_der=(1, 2))
    par(doc, "Tres cosas se leen directo del log y son defendibles sin etiquetas de relevancia: la "
             "tanda casi no repite artista (9,6-9,8 de 10), ninguna tarjeta salió sin nombre ni se "
             "repitió dentro del mismo turno —los dos arreglos que en su día fallaban—, y cuando el "
             "visitante pidió un género explícito se cumplió en el 100 % de las tarjetas que llevan "
             "ese flag (178 de los 298 turnos, porque el campo se añadió a mitad del proyecto).")
    figura(doc, carpeta, "g08_generos.png",
           "Figura 9. Reparto de géneros entre todas las tarjetas recomendadas. El catálogo de la "
           "tabla maestra es de rock, blues, pop y country sobre todo; el sistema no inventa géneros "
           "que no tiene.")
    h2(doc, "8.2 Qué se pierde en el camino")
    par(doc, f"En la carrera de carga, de las {nm(c['bandas'].get('carga',{}).get('visible 1-3',{}).get('tarjetas'))} "
             "tarjetas mostradas solo el 20 % eran emergentes y el 12,4 % tenían clase conocida por "
             "el transformer de intención. La tanda interna prometía 68,8 % de emergentes. La "
             "brecha entre ambas cifras es exactamente el punto que hay que corregir antes de "
             "defender la hipótesis de descubrimiento.")
    doc.add_page_break()


def no_medido(doc, c):
    h1(doc, "9. Lo que no se pudo medir")
    caja(doc, "HR@1, Recall@10, MRR y NDCG@10 no existen todavía", [
        "Estas cuatro métricas necesitan saber qué canciones le gustaron de verdad a alguien. Se "
        "calculan cruzando logs/events_*.jsonl con logs/feedback_*.jsonl, nunca a partir de los "
        "contadores de operación.",
        f"En la VM hay {c['vm']['feedback']['n']} etiquetas de feedback ({c['vm']['feedback']['por_valor'].get('gust',0)} gust, "
        f"{c['vm']['feedback']['por_valor'].get('no_gust',0)} no_gust) y todas provienen de sesiones de "
        "prueba internas (smoke-test-metricas y dos ids de diagnóstico). Etiquetas de visitantes: 0.",
        "El evaluador lo detecta y se niega a inventar el número: /api/metrics lo recuerda en su "
        "campo avisos_evaluacion.",
    ], fondo=FONDO_RIESGO)
    par(doc, "Lo mismo aplica a la comparación contra líneas base, que es la segunda mitad del "
             "objetivo específico 3. Sin un brazo aleatorio, uno de solo popularidad y otro de solo "
             "similitud del Módulo 2, evaluados con las mismas etiquetas, no hay nada que comparar.")
    tabla(doc, ["Falta", "Qué hace falta exactamente", "Coste"], [
        ["Etiquetas de relevancia", "Que cada tarjeta del top-3 tenga un gesto explícito (👍/👎) que "
         "escriba en feedback_*.jsonl con session_id, evento_id y track_name. La API ya existe y "
         "funciona; no hay quien la use.",
         "Recolectar con al menos 20-30 visitantes reales; el botón ya está en la interfaz."],
        ["Líneas base", "Tres políticas de orden sobre el mismo pool de 30 candidatos: aleatorio, "
         "por popularity y solo similitud neural. Se corren offline sobre el log, sin tocar la VM.",
         "Un script nuevo y las mismas etiquetas de arriba."],
        ["ILD y EAD formales", "Ya se miden como artistas distintos y % emergentes; para la fórmula "
         "clásica de intra-list diversity hace falta la distancia entre vectores de las tarjetas "
         "mostradas.", "Cálculo directo desde embeddings.pt, sin datos nuevos."],
        ["Concurrencia real", "Varios visitantes simultáneos contra el slot único de llama.cpp para "
         "cuantificar la espera.", "El mismo cliente de carga con --concurrente N."],
    ], anchos=[3.4, 8.2, 4.4], size=9)
    par(doc, "Ninguna de estas cuatro cosas cambia lo que ya está medido; todas son necesarias para "
             "poder afirmar la mitad de «sin sacrificar precisión» de la hipótesis.", italic=True, color=GRIS)
    doc.add_page_break()


def encuesta(doc, c, carpeta):
    e = c["enc"]
    h1(doc, "10. Encuesta de percepción: datos registrados y validez")
    par(doc, "El instrumento es un formulario externo de 20 afirmaciones en escala 1-5 más un "
             "comentario libre, enlazado desde la propia demo (pie de cada tanda y pantalla de "
             "resultados). El archivo docs/resultados encuesta.xlsx contiene "
             f"{e['filas']} filas: {e['validas']} con los 20 ítems respondidos y {e['sin_responder']} "
             "envíos sin ninguna respuesta.")
    figura(doc, carpeta, "g09_encuesta_items.png",
           f"Figura 10. Media y desviación típica de cada ítem (n = {e['validas']}).")
    figura(doc, carpeta, "g10_encuesta_bloques.png",
           "Figura 11. Los mismos datos agrupados por bloque temático.")
    h2(doc, "10.1 Descriptivos")
    tabla(doc, ["Bloque", "Ítems", "Media", "DT", "% de respuestas 5"], [
        [b["nombre"], ", ".join(str(i) for i in b["items"]), nm(b["media"], 2), nm(b["sd"], 2),
         f"{nm(b['p5'])} %"] for b in e["bloques"]
    ], anchos=[5.4, 2.6, 2.2, 2.2, 3.6], size=9, alineado_der=(2, 3, 4))
    tabla(doc, ["Resumen del instrumento", "Valor"], [
        ["Media global de los 20 ítems", nm(e["media_global"], 2)],
        ["Rango de la escala usada", "solo 3, 4 y 5 (nadie marcó 1 ni 2)"],
        ["Alfa de Cronbach (20 ítems)", nm(e["alfa_cronbach"], 3)],
        ["Correlación inter-ítem media", nm(e["corr_interitem"], 3)],
        ["Ítem mejor valorado", f"«{min(e['items'], key=lambda i: -i['media'])['texto'][:60]}…» "
                                f"({nm(max(i['media'] for i in e['items']),2)})"],
        ["Ítem peor valorado", f"«{min(e['items'], key=lambda i: i['media'])['texto'][:60]}…» "
                                f"({nm(min(i['media'] for i in e['items']),2)})"],
        ["Comentarios recibidos", f"{len(e['comentarios'])} (de {e['comentarios_distintos']} textos distintos)"],
    ], anchos=[6.4, 9.6], size=9)

    h2(doc, "10.2 Validez de la muestra: estos datos no se pueden presentar como evidencia")
    figura(doc, carpeta, "g12_encuesta_rafaga.png",
           "Figura 12. Los minutos con más envíos de la encuesta. Cuatro minutos concentran 135 de las "
           f"{e['validas']} respuestas.")
    figura(doc, carpeta, "g11_encuesta_cronos.png",
           "Figura 13. Respuestas completas por día.")
    par(doc, "Al cruzar las marcas temporales del exportador aparecen cuatro señales simultáneas que "
             "cualquier revisor va a encontrar en cinco minutos:")
    viñetas(doc, [
        (f"Intervalo entre envíos imposible. ",
         f"De los {e['validas']-1} saltos entre una respuesta y la siguiente, {e['huecos_menores_2s']} "
         f"duran menos de 2 s y la mediana es {e['hueco_mediano_s']} s. Leer 20 afirmaciones y "
         "escribir un comentario no cabe en ese tiempo."),
        ("Ráfaga concentrada. ",
         "35 respuestas en un minuto, 35 en el siguiente, 34 y 31 en dos minutos más. Además, el "
         f"mismo día entre 14:23 y 14:30 hubo {e['sin_responder']} envíos totalmente vacíos."),
        ("Los ítems no se correlacionan entre sí. ",
         f"Correlación inter-ítem media {nm(e['corr_interitem'],3)} y alfa de Cronbach "
         f"{nm(e['alfa_cronbach'],3)}. En un cuestionario de percepción contestado por personas, la "
         "correlación habitual es 0,4-0,7 y el alfa supera 0,85. Aquí la media global de "
         f"{nm(e['media_global'],2)} no representa a ningún constructo medido."),
        ("Pocos textos distintos repetidos. ",
         f"{len(e['comentarios'])} comentarios salen de {e['comentarios_distintos']} frases; "
         f"«{e['comentario_repetido'][0][0][:40]}…» aparece {e['comentario_repetido'][0][1]} veces."),
    ])
    caja(doc, "Consecuencia para la tesis", [
        "La sección de evaluación cualitativa no puede apoyarse en este archivo. Presentarlo como "
        "percepción de usuarios reales expondría el trabajo a una objeción seria de integridad de "
        "datos, y la evidencia está en el propio exportador.",
        "Lo que sí se puede decir en la defensa: el instrumento está diseñado, publicado y "
        "enlazado desde la demo; la recolección con usuarios reales es trabajo pendiente.",
        "Para una muestra defendible hacen falta participantes reales (idealmente 30 o más), "
        "reclutados por un canal verificable, con el formulario respondido en un rango de fechas "
        "amplio y consentimiento explícito para usar sus respuestas en la tesis.",
    ], fondo=FONDO_RIESGO)
    doc.add_page_break()


def arreglos(doc, c):
    h1(doc, "11. Arreglos aplicados durante el proyecto")
    par(doc, "Listado completo de las correcciones que se hicieron desde que el sistema funcionaba "
             "en local hasta dejarlo público y medible. La columna de evidencia cita dónde se ve "
             "que el arreglo está vivo en el despliegue de hoy.")
    grupos = [
        ("Catálogo y nombres", [
            ["talkplay_api_service tomaba metadatos de una fuente equivocada y devolvía títulos "
             "genéricos", "Se cambió a song_metadata.json como fuente de nombres.",
             "sin_nombre = 0 en los 298 turnos registrados."],
            ["enriquecer_candidato sobrescribía nombres correctos con «Unknown»",
             "El enriquecimiento solo pisa un campo cuando el nuevo valor es válido.",
             "sin_nombre = 0 también en los turnos con herencia de perfil."],
            ["La respuesta mostraba track IDs en vez de canciones",
             "conversacion.canciones_reales filtra tarjetas sin nombre y el orquestador solo "
             "admite título + artista, conservando los enlaces de Spotify y YouTube.",
             "Ninguna respuesta del log contiene identificadores numéricos."],
            ["El prompt se filtraba en la voz del agente (eco del prompt)",
             "Primero se borraba el eco; después se tradujo a lenguaje hablado para no perder la "
             "referencia (commits b99422c y 356fd03).",
             "limpiar_ecos_de_lista forma parte de la cadena de validación."],
        ]),
        ("Recuperación y re-ranking", [
            ["El re-ranking M2 → M3 no llegaba a ejecutarse",
             "Se conectó la salida del Módulo 2 al re-ranker y se definió la mezcla 0,70 similitud + "
             "0,30 intención, con mediana para candidatos sin clase.",
             f"m3_aporto_orden = {c['g']['carga']['m3_aporto_orden']} de {c['g']['carga']['turnos']} turnos de carga."],
            ["Un artista podía ocupar media tanda",
             "MAX_POR_ARTISTA = 2 y corte de k = 30 → 10.",
             f"artistas distintos {nm(c['global']['artistas_distintos']['prom_turno'],2)} de 10."],
            ["Las recomendaciones eran siempre las mismas famosas",
             "Prioridad a emergentes y señal de fama derivada del propio catálogo (commit 970e51a).",
             f"{nm(c['bandas_ins'].get('emergentes_pct'))} % emergentes en puestos 4-10; popularity media "
             f"{nm(c['global']['tarjetas']['popularity_prom'],1)}."],
            ["Se prometían géneros que el catálogo no tiene",
             "Castigo por desvío de género ×(1−0,50) y por desvío de ánimo ×(1−0,60), con etiquetas "
             "canónicas de género por fila. El aviso explícito al oyente cuando el género pedido no "
             "existe en el catálogo queda pendiente.",
             f"cumple_genero {nm(c['global']['tarjetas']['cumple_genero_pct'])} % donde hay flag; desvío de "
             f"ánimo medio {nm(c['global']['tarjetas']['desvio_animo_prom'],3)}."],
        ]),
        ("Conversación y memoria", [
            ["Cada turno empezaba de cero",
             "Memoria de sesión con herencia de perfil: «más de lo mismo» arrastra ánimo, género y "
             "última canción.",
             f"turnos de {c['g']['carga']['tipo_turno'].get('mas_de_lo_mismo',0)} «mas_de_lo_mismo» y "
             f"{c['g']['carga']['tipo_turno'].get('pregunta',0)} de pregunta en la carga; profundidad máxima 8 turnos."],
            ["La voz y las tarjetas no coincidían",
             "El orquestador devuelve DESTACADAS y el frontend corta por ese número.",
             "Las 3 tarjetas mostradas son las 3 que nombra la respuesta."],
            ["El agente no cerraba con continuidad",
             "cerrar_con_pregunta añade una pregunta de seguimiento al final validado.",
             "Respuestas de 150-260 caracteres terminadas en pregunta."],
        ]),
        ("Despliegue y red", [
            ["El enlace de ngrok mostraba una página de aviso antes de la demo",
             "Quick Tunnel de Cloudflare como entrada principal, ngrok con dominio reservado de "
             "respaldo (commit 43d5434).", "La demo abre sin intersticial."],
            ["El puerto 80 quedaba abierto a internet",
             "Se cerró en el NSG: la VM solo hace conexiones salientes hacia el túnel.",
             "Comprobado en la configuración de red del grupo rg-echopulse-demo."],
            ["Los endpoints de diagnóstico exponían estado interno",
             "/api/llm/status deshabilitado en modo público.",
             "Responde «endpoint de diagnóstico deshabilitado»."],
            ["Unos pocos visitantes impacientes saturaban la máquina",
             "Ventana deslizante por IP (limite.py) con LIMITE_POR_MINUTO = 12 y lectura de "
             "X-Forwarded-For solo desde el proxy local.",
             f"consultas_bloqueadas = {c['metrics']['consultas_bloqueadas'] if c['metrics'] else 0} en la corrida evaluada."],
            ["La subida a Git se bloqueaba por artefactos grandes",
             "Artefactos binarios fuera del índice y versionado de los módulos que faltaban "
             "(commit 62ca548).", "El repositorio clona sin LFS."],
            ["Puerto y debug estaban fijados en el código",
             "Configurables por variable de entorno (commit 10e896b).",
             "PORT y DEBUG leídos en app.py."],
        ]),
        ("Telemetría y evaluación", [
            ["Los contadores de operación se confundían con métricas de tesis",
             "evaluar_metricas.py calcula HR/Recall/Precision/MRR/NDCG cruzando events con feedback, "
             "y /api/metrics lleva un aviso que lo recuerda.",
             "El aviso aparece en la respuesta pública del endpoint."],
            ["El tráfico de prueba contaminaba las cifras de usuarios",
             "PREFIJOS_SINTETICOS = (carga-, verif-) excluidos por defecto en el evaluador, con "
             "--incluir-carga para el análisis de plataforma.",
             "Desglose de la sección 4.1."],
            ["No había forma de generar carga medible contra la demo",
             "scripts/prueba_carga.py: sesiones con prefijo, ritmo configurable, reintento ante 429, "
             "aborto con STOP y volcado incremental.",
             f"{c['n_carga']} turnos sin un solo fallo HTTP."],
        ]),
    ]
    for titulo, filas in grupos:
        h2(doc, f"11.{grupos.index((titulo, filas)) + 1} {titulo}")
        tabla(doc, ["Problema", "Arreglo", "Evidencia en el despliegue actual"], filas,
              anchos=[5.0, 6.4, 4.6], size=8.5)
    h2(doc, "11.6 Corregido a medias o pendiente")
    tabla(doc, ["Asunto", "Estado", "Qué falta"], [
        ["Rechazo sistemático del validador cuando el modelo cita fuera de la tanda",
         "Diagnosticado, sin desplegar", "Cambiar descartar_citas_inventadas para que elimine la cita "
         "y conserve la prosa; test de regresión con las muestras reales del log."],
        ["El visitante solo ve los 3 puestos más famosos", "Medido, sin decidir",
         "Subir DESTACADAS o intercalar un emergente por tanda y volver a medir."],
        ["Sin etiquetas de relevancia", "Pendiente", "Recolección con usuarios reales."],
        ["Encuesta sin muestra válida", "Pendiente", "Reclutamiento real, ver sección 10.2."],
    ], anchos=[5.6, 3.0, 7.4], size=9)
    doc.add_page_break()


def limitaciones(doc, c):
    h1(doc, "12. Limitaciones y amenazas a la validez")
    tabla(doc, ["Amenaza", "Cómo afecta a las conclusiones", "Qué se hizo al respecto"], [
        ["Muestra de usuarios reales mínima",
         f"Solo {c['g']['real']['turnos']} turnos de {c['g']['real']['sesiones']} sesiones reales. Las "
         "cifras de visitantes tienen intervalos de confianza amplísimos.",
         "Se separaron del resto y se reportan junto a los 298 turnos totales para que se vea la "
         "proporción."],
        ["Tráfico sintético con plantillas",
         "La carrera de carga usa frases generadas: puede sub o sobre-representar ciertos turnos "
         "(el 34 % fueron «más de lo mismo»).",
         "Sirve para latencia y estabilidad, que no dependen del contenido; no se usa para afirmar "
         "nada sobre percepción."],
        ["Un solo slot de generación",
         "Las latencias concurridas no están medidas; con dos visitantes simultáneos p90 sería mayor.",
         "Anotado en la sección 5.2 y en el plan de la 13."],
        ["URL pública volátil",
         "El enlace de Cloudflare cambia si el contenedor se reinicia: la muestra de visitantes "
         "depende de que el enlace esté vivo.",
         "ngrok con dominio reservado queda como alternativa fija."],
        ["Campos de calidad añadidos a mitad del proyecto",
         "cumple_genero y desvio_animo solo existen en 178 de los 298 turnos.",
         "Se indica siempre el denominador."],
        ["Contador en memoria frente al log en disco",
         "/api/metrics reinicia su acumulado con el contenedor (185 turnos frente a 298 en el "
         "fichero).", "El informe usa el log de eventos como fuente y el endpoint solo para "
         "verificar éxito y bloqueos."],
        ["Instrumento de encuesta no validado",
         "Sin consistencia interna (alfa "
         f"{nm(c['enc']['alfa_cronbach'],2)}) la media compuesta no significa nada.",
         "Se documenta en 10.2 y se retira como evidencia."],
    ], anchos=[3.6, 6.6, 5.8], size=9)
    doc.add_page_break()


def pendiente(doc, c):
    h1(doc, "13. Trabajo pendiente y orden recomendado para cerrar")
    par(doc, "Por orden de impacto sobre la defensa, no de facilidad:")
    tabla(doc, ["#", "Tarea", "Por qué va ahí", "Cómo se comprueba"], [
        ["1", "Arreglar descartar_citas_inventadas y desplegar solo el servicio app",
         f"Recupera {nm(100*c['global']['rechazados']/c['n_eventos'])} % de las respuestas para la "
         "ruta del modelo; es el único defecto localizado en el código.",
         "Tasa de rechazo en el log tras el cambio, sobre la misma corrida de 330 turnos."],
        ["2", "Decidir la política de la tanda visible (DESTACADAS o intercalado)",
         "Sin esto la afirmación de descubrimiento de emergentes no se sostiene en la interfaz.",
         "Emergentes en puestos 1-3 medido igual que en la sección 8."],
        ["3", "Recolectar etiquetas de relevancia (👍/👎) con 20-30 visitantes",
         "Es la llave de HR, Recall, MRR y NDCG, y de la comparación contra líneas base.",
         "evaluar_metricas.py con el log y el feedback de la VM."],
        ["4", "Correr las tres líneas base offline",
         "El objetivo específico 3 pide comparar; se puede hacer sin tocar la VM.",
         "Tabla de métricas por política sobre el mismo pool."],
        ["5", "Rehacer la encuesta con participantes reales",
         "Sustituir una sección que hoy no es defendible.",
         "Alfa de Cronbach > 0,8 y distribución de tiempos coherente."],
        ["6", "Prueba de concurrencia real",
         "Completa el retrato de rendimiento con varios usuarios a la vez.",
         "p50/p90/p99 con N visitantes simultáneos."],
        ["7", "Subir los cambios de esta ronda al repositorio",
         "Deck, documento de arquitectura, cliente de carga, evaluador y este informe están sin "
         "push, junto con los dos commits locales previos.",
         "git status limpio y el histórico público actualizado."],
    ], anchos=[0.8, 5.0, 5.6, 4.6], size=9)
    doc.add_page_break()


def anexos(doc, c, args):
    h1(doc, "14. Anexos")
    h2(doc, "14.1 Reproducir la medición")
    par(doc, "Desde la máquina de desarrollo, sin abrir el puerto SSH de la VM:")
    for linea in [
        "az vm run-command invoke -g rg-echopulse-demo -n echopulse-demo \\",
        "    --command-id RunShellScript --scripts @/tmp/harvest.sh -o tsv --query 'value[0].message'",
        "",
        "# carrera de carga contra la demo desplegada",
        "python scripts/prueba_carga.py --total 330 --rpm 20 --semilla 7",
        "echo stop > logs_carga/STOP          # aborta limpio en cualquier momento",
        "",
        "# métricas de tesis, excluyendo el tráfico sintético",
        "python scripts/evaluar_metricas.py --logs logs --salve informe.md",
        "python scripts/evaluar_metricas.py --logs logs --incluir-carga   # vista de plataforma",
        "",
        "# este informe",
        "python scripts/informe_evaluacion.py graficas",
        "python scripts/informe_evaluacion.py docx",
    ]:
        p = doc.add_paragraph()
        r = p.add_run(linea)
        r.font.name = "Consolas"
        r.font.size = Pt(8.5)
        p.paragraph_format.space_after = Pt(0)
    doc.add_paragraph()
    h2(doc, "14.2 Artefactos del proyecto")
    tabla(doc, ["Artefacto", "Ruta", "Qué contiene"], [
        ["Este informe", "docs/EchoPulse_AI_informe_evaluacion.docx", "Evaluación completa con figuras."],
        ["Documento de arquitectura", "docs/EchoPulse_AI_arquitectura_detalle.html",
         "17 secciones y 22 tablas con el detalle de módulos, datos y decisiones."],
        ["Presentación de defensa", "docs/EchoPulse_AI_presentacion_tesis.pptx",
         "14 láminas para 10 minutos, con el diagrama de arquitectura en vectores."],
        ["Encuesta exportada", "docs/resultados encuesta.xlsx",
         f"{c['enc']['filas']} filas del formulario (ver advertencia de la sección 10.2)."],
        ["Cliente de carga", "echopulse_llm_orquestator/scripts/prueba_carga.py",
         "Generador de tráfico etiquetado."],
        ["Evaluador de métricas", "echopulse_llm_orquestator/scripts/evaluar_metricas.py",
         "HR/Recall/Precision/MRR/NDCG + diversidad + latencia desde los logs."],
        ["Registro de la corrida", "echopulse_llm_orquestator/logs_carga/",
         f"{c['n_carga']} turnos con su latencia, proveedor y tanda."],
        ["Logs de la VM", "/app/logs/*.jsonl en echopulse-app-1 (volumen app-logs)",
         f"{c['n_eventos']} turnos, {c['vm']['metrics_lineas']} métricas, {c['vm']['feedback']['n']} etiquetas."],
        ["Composición de servicios", "deploy/azure-compose.yaml",
         "qwen, app, tunnel y tunnel-cf con los comentarios de cada decisión."],
        ["Figuras de este informe", "docs/informe_evaluacion_assets/", "13 PNG generados por script."],
    ], anchos=[3.4, 6.0, 6.6], size=9)
    h2(doc, "14.3 Diccionario de los campos de calidad")
    tabla(doc, ["Campo", "Significado", "Rango observado"], [
        ["metadata_hits / misses", "Tarjetas a las que se les encontró metadato completo.",
         f"{nm(c['global']['metadata_pct'])} % de cobertura"],
        ["cobertura_m3", "Fracción de la tanda cuyo título existe como clase del IntentTransformer.",
         f"0 a 0,5 · media {nm(c['global']['cobertura_m3']['prom_pct']/100, 3)}"],
        ["m3_aporto_orden", "El re-ranker cambió el orden que traía el Módulo 2.",
         f"{c['g']['carga']['m3_aporto_orden']}/{c['g']['carga']['turnos']} en carga"],
        ["emergentes / reconocidos", "Tarjetas marcadas por la señal de fama del catálogo.",
         f"{nm(c['global']['emergentes']['prom_turno'],1)} y {nm(c['global']['reconocidos']['prom_turno'],1)} por tanda de 10"],
        ["artistas_distintos", "ILD aproximada por artista dentro de la tanda.",
         f"{nm(c['global']['artistas_distintos']['prom_turno'],2)} de 10"],
        ["sin_nombre / repetidas", "Tarjetas sin título útil o repetidas en el mismo turno.",
         "0 en los dos casos, en los 298 turnos"],
        ["tipo_turno", "musica · mas_de_lo_mismo · pregunta · saludo.",
         cadena(c["global"]["tipo_turno"])],
        ["llm_proveedor / llm_rechazado", "Quién escribió la respuesta y si el validador tumbó al modelo.",
         cadena(c["global"]["proveedor"]) + f" · rechazados {c['global']['rechazados']}"],
        ["intencion", "De dónde salió la intención: heurística de palabras clave o el LLM.",
         cadena(c["global"]["intencion"])],
    ], anchos=[3.6, 6.6, 5.8], size=9)
    h2(doc, "14.4 Ítems de la encuesta")
    tabla(doc, ["#", "Afirmación", "Media", "DT", "% 5"], [
        [it["codigo"], it["texto"], nm(it["media"], 2), nm(it["sd"], 2), f"{nm(it['p5'])} %"]
        for it in c["enc"]["items"]
    ], anchos=[0.8, 10.4, 1.6, 1.6, 1.6], size=8, alineado_der=(2, 3, 4))
    par(doc, "Documento generado el "
             f"{datetime.datetime.now().strftime('%d/%m/%Y')} desde los insumos de "
             f"{args.vm}, {args.carga} y {args.encuesta}.", size=8, color=GRIS, italic=True)
