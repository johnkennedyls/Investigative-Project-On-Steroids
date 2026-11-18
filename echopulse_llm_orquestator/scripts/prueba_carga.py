# scripts/prueba_carga.py - Telemetría de la demo bajo consulta sintética
"""Consume /api/chat N veces con consultas variadas y deja el resultado en JSONL.

Mide lo que el sistema TARDA y lo que ENTREGA cuando nadie está mirando: latencia
por etapa, tasa de error, cobertura del Módulo 3, mezcla emergente/reconocido y
coherencia de género. No escribe en /api/feedback: una máquina no puede dar su
etiqueta de relevancia, así que la carga nunca toca HR@1, MRR ni NDCG.

Las sesiones se rotulan `carga-` y `evaluar_metricas.py` las excluye por defecto,
para que el conteo de visitantes reales siga siendo exactamente eso.

    python scripts/prueba_carga.py --total 300
    python scripts/prueba_carga.py --total 20 --rpm 6 --salida logs_prueba
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

URL_DEMO = "https://zero-programming-opens-detroit.trycloudflare.com/api/chat"

# Un turno real never dice todo en una frase: unas veces nombra género, otras solo
# la actividad, otras contradice lo anterior. Mezclar estas formas es lo que
# ejercita heurísticas, perfil heredado y castigos de ánimo.
ACTIVIDADES = [
    "para estudiar de madrugada", "para el gimnasio", "para cocinar",
    "para manejar de noche", "para leer en el sofá", "para trabajar concentrado",
    "para una reunión con amigos", "para caminar sin rumbo", "para el viaje en bus",
    "para escribir", "para limpiar la casa", "para un domingo flojo",
]
ANIMOS = [
    "bien tranquilo", "un poco melancólico", "alegre", "energético", "íntimo",
    "nostálgico", "relajado", "intenso", "alegre pero sin estridencia",
    "suave", "con ritmo", "deprimido pero bonito",
]
GENEROS = [
    "rock", "blues", "jazz", "pop", "country", "folk", "reggae", "hip hop",
    "soul", "indie", "música electrónica", "punk",
]
EPOCAS = ["de los setenta", "de los ochenta", "de los noventa", "de los dos mil",
          "reciente", "clásico", "de mitad de siglo"]
EXCLUSIONES = ["sin voz femenina", "nada de sintetizadores", "sin rap",
               "nada de música comercial", "nada en español"]

CONTINUACIONES = [
    "dame más", "sigue con eso", "otras parecidas", "más de lo mismo",
    "dasme otras mas movidas", "prefiero algo mas tranquilo",
    "cambia el animo, algo mas intenso", "ahora algo de los ochenta",
    "sin repetir las anteriores", "y para manejar de noche?",
    "algo mas oscuro", "sube el ritmo", "baja el ritmo",
    "cambia de genero, algo de jazz", "solo blues, nada de rock",
]
NO_MUSICOS = [
    "¿qué puedes hacer?", "¿cómo funcionas?", "no entiendo, repite",
    "gracias", "¿de dónde sacas la música?",
]


def _frase_inicial(rng: random.Random) -> str:
    """Un pedido con nombre y apellido: los usuarios reales no usan siempre la misma forma."""
    forma = rng.randint(1, 7)
    animo, actividad, genero, epoca = (rng.choice(ANIMOS), rng.choice(ACTIVIDADES),
                                       rng.choice(GENEROS), rng.choice(EPOCAS))
    if forma == 1:
        return f"pon algo {animo} {actividad}"
    if forma == 2:
        return f"quiero {genero} {animo} {actividad}"
    if forma == 3:
        return f"buscame canciones {epoca} de {genero} que esten {animo}"
    if forma == 4:
        return f"necesito música para {actividad.replace('para ', '')}, algo {animo}"
    if forma == 5:
        return f"recomiéndame {genero} {epoca}, {rng.choice(EXCLUSIONES)}"
    if forma == 6:
        return f"¿me pones algo {animo}?, no quiero {genero} comercial"
    return f"anima la tarde con {genero} {epoca} {animo}"


def construir_turnos(total: int, semilla: int) -> list[dict]:
    """Serie de (sesión, turno) con sesiones de 1 a 4 turnos, como en la vida real."""
    rng = random.Random(semilla)
    turnos, n, contador_sesion = [], 0, 0
    while n < total:
        contador_sesion += 1
        duracion = min(rng.choice([1, 2, 2, 3, 3, 4]), total - n)
        if duracion <= 0:
            break
        sesion = f"carga-{datetime.now().strftime('%y%m%d')}-{contador_sesion:04d}"
        anterior = ""
        for indice in range(duracion):
            if indice == 0:
                mensaje = _frase_inicial(rng)
            else:
                mensaje = rng.choice(CONTINUACIONES + [_frase_inicial(rng) * 3])
                if mensaje == anterior:
                    mensaje = rng.choice(CONTINUACIONES)
            anterior = mensaje
            turnos.append({"sesion": sesion, "indice": indice + 1, "mensaje": mensaje[:500]})
            n += 1
    return turnos


def llamar(url: str, sesion: str, mensaje: str, timeout: float) -> dict:
    cuerpo = json.dumps({"session_id": sesion, "message": mensaje}).encode("utf-8")
    req = request.Request(url, data=cuerpo, headers={"Content-Type": "application/json"})
    inicio = time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            bruto = resp.read().decode("utf-8", "replace")
            estado, registro = resp.status, json.loads(bruto)
    except error.HTTPError as exc:
        return {"http_status": exc.code, "ok": False,
                "ms_total": round((time.perf_counter() - inicio) * 1000, 1),
                "error": exc.read().decode("utf-8", "replace")[:200]}
    except Exception as exc:
        return {"http_status": 0, "ok": False,
                "ms_total": round((time.perf_counter() - inicio) * 1000, 1),
                "error": f"{type(exc).__name__}: {exc}"}

    ms_total = round((time.perf_counter() - inicio) * 1000, 1)
    tanda = (registro.get("module3_reranked") or [])[:int(registro.get("destacadas") or 0) or 10]
    return {
        "http_status": estado, "ok": estado == 200 and bool(registro.get("response")),
        "ms_total": ms_total,
        "ms_servidor": (registro.get("latencies_ms") or {}).get("total"),
        "query_en": registro.get("query_en"),
        "llm": (registro.get("llm") or {}).get("proveedor"),
        "intencion": (registro.get("llm") or {}).get("intencion"),
        "pistas": len(tanda),
        "con_clase_m3": sum(1 for c in tanda if c.get("intent_conocida")),
        "emergentes": sum(1 for c in tanda if c.get("emergente")),
        "reconocidos": sum(1 for c in tanda if c.get("reconocido")),
        "artistas_distintos": len({(c.get("artist_name") or "").lower() for c in tanda}),
        "generos_distintos": len({g for c in tanda for g in (c.get("generos") or [])}),
        "cumple_genero": sum(1 for c in tanda if c.get("cumple_genero")),
        "desvios_animo": [c.get("desvio_animo") for c in tanda if c.get("desvio_animo") is not None],
        "respuesta": (registro.get("response") or "")[:400],
        "error": registro.get("error"),
    }


def percentil(valores: list[float], q: float) -> float:
    if not valores:
        return 0.0
    orden = sorted(valores)
    return round(orden[min(len(orden) - 1, max(0, int(round(q * (len(orden) - 1)))))], 1)


def resumir(registros: list[dict], desde: float) -> dict:
    ok = [r for r in registros if r["ok"]]
    fallidos = [r for r in registros if not r["ok"]]
    lat = [r["ms_total"] for r in ok]
    serv = [r["ms_servidor"] for r in ok if r.get("ms_servidor")]
    desvio = [d for r in ok for d in (r.get("desvios_animo") or [])]
    total_pistas = sum(r["pistas"] for r in ok)
    return {
        "enviados": len(registros), "exitosos": len(ok), "fallidos": len(fallidos),
        "duracion_min": round((time.time() - desde) / 60, 1),
        "turnos_por_minuto": round(len(registros) / max((time.time() - desde) / 60, 0.001), 2),
        "latencia_client_ms": {"p50": percentil(lat, 0.5), "p90": percentil(lat, 0.9),
                               "p99": percentil(lat, 0.99), "promedio": round(statistics.mean(lat), 1) if lat else 0},
        "latencia_servidor_ms": {"p50": percentil(serv, 0.5), "p90": percentil(serv, 0.9)},
        "caidas_http": {str(c): sum(1 for r in fallidos if r["http_status"] == c)
                        for c in {r["http_status"] for r in fallidos}},
        "pistas_entregadas": total_pistas,
        "emergentes_pct": round(100 * sum(r["emergentes"] for r in ok) / total_pistas, 1) if total_pistas else 0,
        "reconocidos_pct": round(100 * sum(r["reconocidos"] for r in ok) / total_pistas, 1) if total_pistas else 0,
        "con_clase_m3_pct": round(100 * sum(r["con_clase_m3"] for r in ok) / total_pistas, 2) if total_pistas else 0,
        "artistas_distintos_promedio": round(statistics.mean([r["artistas_distintos"] for r in ok]), 2) if ok else 0,
        "generos_distintos_promedio": round(statistics.mean([r["generos_distintos"] for r in ok]), 2) if ok else 0,
        "cumple_genero_pct": round(100 * sum(r["cumple_genero"] for r in ok) / total_pistas, 1) if total_pistas else 0,
        "desvio_animo_promedio": round(statistics.mean(desvio), 3) if desvio else None,
        "turnos_llm": sum(1 for r in ok if (r.get("llm") or "").lower() not in ("", "determinista", "none")),
        "turnos_deterministas": sum(1 for r in ok if (r.get("llm") or "").lower() in ("determinista", "", "none")),
        "intencion_desde_llm": sum(1 for r in ok if r.get("intencion") == "llm"),
        "intencion_desde_heuristica": sum(1 for r in ok if r.get("intencion") == "heuristica"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Consumo sintético de /api/chat con rótulo `carga-`.")
    ap.add_argument("--total", type=int, default=300)
    ap.add_argument("--url", default=URL_DEMO)
    ap.add_argument("--rpm", type=float, default=10.0,
                    help="tope de turnos por minuto; el servidor corta en 12 por IP")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--semilla", type=int, default=20261029)
    ap.add_argument("--salida", default="logs_carga")
    args = ap.parse_args()

    carpeta = Path(args.salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    parada = carpeta / "STOP"
    marca = datetime.now().strftime("%y%m%d-%H%M%S")
    ruta_jsonl = carpeta / f"carga_{marca}.jsonl"

    plan = construir_turnos(args.total, args.semilla)
    intervalo = 60.0 / args.rpm if args.rpm > 0 else 0
    print(f"▶ {len(plan)} turnos en {len({t['sesion'] for t in plan})} sesiones "
          f"({args.rpm}/min · tope del servidor 12/min) → {ruta_jsonl}")

    registros, inicio = [], time.time()
    with open(ruta_jsonl, "a", encoding="utf-8") as f:
        for position, turno in enumerate(plan, start=1):
            if parada.exists():
                print("⏹ archivo STOP detectado: cierro y resumo lo hecho.")
                break
            ronda = time.perf_counter()
            resultado = llamar(args.url, turno["sesion"], turno["mensaje"], args.timeout)
            if resultado["http_status"] == 429:
                time.sleep(20)
                resultado = llamar(args.url, turno["sesion"], turno["mensaje"], args.timeout)
                resultado["reintento_429"] = True
            registro = {"timestamp": datetime.now(timezone.utc).isoformat(), **turno, **resultado}
            registros.append(registro)
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
            f.flush()
            bandera = "✅" if resultado["ok"] else "❌"
            print(f"{bandera} {position:4d}/{len(plan)} {resultado['ms_total']:7.0f}ms "
                  f"{turno['sesion'][-4:]}/{turno['indice']} {turno['mensaje'][:42]} "
                  f"→ {resultado.get('pistas', 0)} pistas · em {resultado.get('emergentes', 0)}")
            time.sleep(max(0.0, intervalo - (time.perf_counter() - ronda)))

    resumen = resumir(registros, inicio)
    ruta_resumen = carpeta / f"carga_{marca}_resumen.json"
    ruta_resumen.write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    print(f"📄 resumen en {ruta_resumen}")
    return 0 if resumen["fallidos"] <= len(registros) * 0.05 else 1


if __name__ == "__main__":
    sys.exit(main())
