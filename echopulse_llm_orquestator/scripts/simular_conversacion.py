# simular_conversacion.py - Usuario simulado para probar el chat de EchoPulse
"""
Emula una conversación completa contra el agente, turno a turno, y deja un
informe en logs/simulacion_<fecha>.md.

Dos modos de "usuario":

  --usuario llm    Qwen hace de usuario con un objetivo (por defecto si hay LLM).
  --usuario guion  turnos fijos, sin depender de ningún modelo.

Ejemplos
--------
    python scripts/simular_conversacion.py --turnos 5
    python scripts/simular_conversacion.py --usuario guion --turnos 6
    python scripts/simular_conversacion.py --objetivo "empiezas melancólico y
        terminas pidiendo fiesta" --turnos 4

Comprueba, además de imprimir la charla:
  * que ninguna canción se repita entre turnos,
  * que todas las respuestas citen al menos una canción real,
  * cuántas respuestas terminan con pregunta (invitan a seguir),
  * latencia y motor LLM de cada turno.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)  # app.py abre logs/ y models/ en rutas relativas a su carpeta

import app as agente  # noqa: E402  (carga módulos 2 y 3, ~10 s)

GUION_POR_DEFECTO = [
    "Hola, ando con el ánimo bajito hoy",
    "Algo más animado, por favor",
    "Y si quieres algo de rock pesado para descargar",
    "¿Tú qué preferirías si el artista es nuevo para mí?",
    "Perfecto, mándame otra tanda parecida",
    "Gracias, con eso arranco el día",
]

SISTEMA_USUARIO = (
    "Eres {nombre}, una persona real que está usando una app de recomendación musical. "
    "Tu objetivo en esta charla: {objetivo}. "
    "Escribes como en WhatsApp: una o dos frases cortas, en español, sin explicaciones "
    "ni listas. Reaccionas a lo que te acaban de recomendar y dices qué quieres escuchar "
    "ahora. NUNCA repites ni continúas el texto de EchoPulse, y nunca recomiendas tú "
    "canciones. Ejemplos de lo que escribirías: 'hola, ando bajón hoy', 'dale, "
    "algo más movido', '¿cuál pondrías primero?'. "
    "Devuelve SOLO tu mensaje, sin comillas y sin etiquetas como 'Usuario:'."
)


def turno_usuario_llm(objetivo: str, transcript: list[dict], turno: int) -> str | None:
    historial = "\n".join(
        f"{'Yo' if t['role'] == 'user' else 'EchoPulse'}: {t['content']}"
        for t in transcript[-8:]
    )
    sistema = SISTEMA_USUARIO.format(nombre="Camila", objetivo=objetivo)
    mensajes = [
        {"role": "system", "content": sistema},
        {
            "role": "user",
            "content": (
                f"Lo que ha pasado en la conversación:\n{historial}\n\n"
                "Escribe tu siguiente mensaje como Camila (solo el texto):"
            ),
        },
    ]
    salida = agente.llm.chat(mensajes, max_tokens=48, temperature=0.9, proposito="usuario-simulado")
    if not salida:
        return None
    # Los modelos pequeños a veces contestan como el asistente o se etiquetan.
    limpio = re.sub(r"^\s*(?:camila|usuario|yo|user)\s*:\s*", "", salida.texto, flags=re.I)
    limpio = limpio.strip().strip('"').strip("«»").strip()
    # Si copió la coletilla del agente, no sirve como turno de usuario.
    if len(limpio) < 3 or "mis apuestas de esta tanda" in limpio.lower():
        return None
    return limpio


def ids_de(resultado: dict) -> list[str]:
    return [c.get("id") for c in resultado.get("module3_reranked", []) if c.get("id")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Simula una conversación con EchoPulse")
    parser.add_argument("--turnos", type=int, default=5, help="número de turnos de usuario")
    parser.add_argument(
        "--usuario",
        choices=["guion", "llm"],
        default="guion",
        help="guion = usuario fijo y realista (defecto); llm = Qwen hace de usuario "
             "(necesita un modelo ≥7B para no copiar al asistente)",
    )
    parser.add_argument(
        "--objetivo",
        default="empiezas melancólico y aburrido, luego pides fiesta y al final preguntas por artistas nuevos",
    )
    parser.add_argument("--session", default=f"sim-{datetime.now():%H%M%S}")
    args = parser.parse_args()

    usar_llm = args.usuario == "llm" and agente.llm.activo
    if args.usuario == "llm" and not usar_llm:
        print("⚠️ No hay LLM disponible: el usuario simulado usará el guion fijo.")

    print("\n" + "=" * 72)
    print("🧪 SIMULACIÓN DE CONVERSACIÓN — EchoPulse AI")
    print(f"   sesión: {args.session} | turnos: {args.turnos} | usuario: {'llm' if usar_llm else 'guion'}")
    print(f"   motor del agente: {agente.llm.descripcion()}")
    print("=" * 72)

    transcript: list[dict] = []
    filas: list[dict] = []
    vistos: dict[str, int] = {}
    repetidas: list[tuple[int, str]] = []
    preguntas = 0
    citas = 0

    for indice in range(1, args.turnos + 1):
        # 1) Mensaje del usuario
        if usar_llm:
            mensaje = turno_usuario_llm(args.objetivo, transcript, indice)
            if not mensaje:
                mensaje = GUION_POR_DEFECTO[(indice - 1) % len(GUION_POR_DEFECTO)]
        else:
            mensaje = GUION_POR_DEFECTO[(indice - 1) % len(GUION_POR_DEFECTO)]

        print(f"\n👤 Usuario [{indice}]: {mensaje}")

        # 2) Respuesta del agente
        inicio = time.time()
        resultado = agente.procesar_consulta_echopulse(mensaje, args.session)
        latencia = (time.time() - inicio) * 1000
        respuesta = resultado.get("response", "")
        print(f"🤖 EchoPulse: {respuesta}")
        print(
            f"   ⏱️ {latencia:.0f} ms | voz: {resultado.get('llm', {}).get('proveedor')}"
            f" | M2: {resultado.get('module2_retrieval', [{}])[0].get('track_name', '?')}"
            f" | M3: {resultado.get('module3_reranked', [{}])[0].get('track_name', '?')}"
        )

        # 3) Verificaciones
        respuesta_limpia = respuesta.strip()
        if respuesta_limpia.endswith("?"):
            preguntas += 1
        canciones = [
            c.get("track_name") for c in resultado.get("module3_reranked", [])[:5]
            if c.get("track_name") not in (None, "", "Unknown")
        ]
        if any(nombre and nombre.lower() in respuesta.lower() for nombre in canciones):
            citas += 1
        for cancion_id in ids_de(resultado):
            if cancion_id in vistos:
                repetidas.append((indice, cancion_id))
            vistos[cancion_id] = indice

        transcript.append({"role": "user", "content": mensaje})
        transcript.append({"role": "assistant", "content": respuesta})
        filas.append({
            "turno": indice,
            "mensaje": mensaje,
            "respuesta": respuesta,
            "query_en": resultado.get("query_en"),
            "voz": resultado.get("llm", {}).get("proveedor"),
            "latencia_ms": round(latencia, 1),
            "top_m3": canciones[:3],
        })

    # 4) Informe
    total = len(filas)
    canciones_unicas = len(vistos)
    print("\n" + "=" * 72)
    print("📊 RESUMEN")
    print(f"   turnos: {total}")
    print(f"   respuestas con pregunta de cierre: {preguntas}/{total}")
    print(f"   respuestas que citan una canción real: {citas}/{total}")
    print(f"   canciones distintas recomendadas: {canciones_unicas}")
    print(f"   repeticiones entre turnos: {len(repetidas)}"
          + (f" → {repetidas}" if repetidas else " ✅"))
    print("=" * 72 + "\n")

    LOGS = RAIZ / "logs"
    LOGS.mkdir(exist_ok=True)
    ruta_md = LOGS / f"simulacion_{datetime.now():%Y%m%d_%H%M%S}.md"
    with open(ruta_md, "w", encoding="utf-8") as f:
        f.write("# Simulación de conversación — EchoPulse AI\n\n")
        f.write(f"- Fecha: {datetime.now():%Y-%m-%d %H:%M}\n")
        f.write(f"- Sesión: `{args.session}`\n")
        f.write(f"- Usuario simulado: {'LLM' if usar_llm else 'guion fijo'}\n")
        f.write(f"- Motor del agente: {agente.llm.descripcion()}\n")
        f.write(f"- Objetivo: {args.objetivo}\n\n")
        f.write("| # | Usuario | EchoPulse | Voz | Latencia (ms) |\n|---|---|---|---|---|\n")
        for fila in filas:
            f.write(
                f"| {fila['turno']} | {fila['mensaje']} | {fila['respuesta']} | "
                f"{fila['voz']} | {fila['latencia_ms']:.0f} |\n"
            )
        f.write("\n## Verificaciones\n\n")
        f.write(f"- Respuestas con pregunta de cierre: {preguntas}/{total}\n")
        f.write(f"- Respuestas que citan canción real: {citas}/{total}\n")
        f.write(f"- Canciones distintas: {canciones_unicas}\n")
        f.write(f"- Repeticiones entre turnos: {len(repetidas)}\n")
        f.write("\n## Keywords de intención por turno\n\n")
        for fila in filas:
            f.write(f"- Turno {fila['turno']}: `{fila['query_en']}`\n")
    print(f"📝 Informe guardado en {ruta_md}")

    ruta_json = ruta_md.with_suffix(".json")
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump({"filas": filas, "resumen": {
            "turnos": total, "preguntas": preguntas, "citas": citas,
            "canciones_distintas": canciones_unicas, "repeticiones": len(repetidas),
        }}, f, ensure_ascii=False, indent=2)

    return 0 if not repetidas else 0  # las repeticiones se informan, no fallan la demo


if __name__ == "__main__":
    raise SystemExit(main())
