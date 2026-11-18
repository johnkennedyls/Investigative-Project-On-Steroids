# scripts/cliente_evaluacion.py - Turnos de evaluación contra la demo desplegada
"""Consume /api/chat y guarda el evento COMPLETO de cada turno, no un resumen.

`prueba_carga.py` mide operación (latencia, errores, mezcla) y recorta la tanda a
las tarjetas visibles, así que de sus registros no se puede reconstruir un
ranking. Las métricas de orden (HR@1, Recall@10, MRR, NDCG@10) necesitan las diez
posiciones que devuelve el re-ranker y el perfil que el Módulo 2 prometió
cumplir. Este cliente guarda ambas cosas con el mismo esquema que el JSONL del
servidor, de modo que `evaluar_ranking.py` los lee sin cambios.

No escribe en /api/feedback: una máquina no puede emitir una etiqueta de
relevancia. La relevancia se deriva del catálogo (afinidad de contenido
verificable), no de la opinión del cliente.

    python scripts/cliente_evaluacion.py --total 330
    python scripts/cliente_evaluacion.py --total 12 --rpm 6 --salida build/eva/prueba

Para detener una corrida larga: crear el archivo STOP dentro de --salida.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prueba_carga import (  # noqa: E402  (banco de consultas ya validado)
    CONTINUACIONES, NO_MUSICOS, _frase_inicial, percentil,
)

URL_DEMO = "https://zero-programming-opens-detroit.trycloudflare.com/api/chat"
RAIZ = Path(__file__).resolve().parents[2]

# Campos del ranking que el servidor registra por turno. Se copian tal cual para
# que el evaluador offline no distinga entre un evento del log y uno del cliente.
CAMPOS_TARJETA = (
    "rank", "id", "track_name", "artist_name", "genre", "generos",
    "cumple_genero", "desvio_animo", "similarity", "intent_score",
    "intent_conocida", "final_score", "emergente", "reconocido", "popularity",
)


def construir_turnos(total: int, semilla: int, marca: str) -> list[dict]:
    """Sesiones de 2 a 5 turnos: la herencia de perfil solo se ejercita si hay
    continuación, y un turno suelto no permite medir repetición entre tandas."""
    rng = random.Random(semilla)
    turnos: list[dict] = []
    contador = 0
    while len(turnos) < total:
        contador += 1
        restantes = total - len(turnos)
        duracion = min(rng.choice([2, 3, 3, 4, 4, 5]), restantes)
        sesion = f"eval-{marca}-{contador:04d}"
        anterior = ""
        for indice in range(duracion):
            if indice == 0:
                mensaje = _frase_inicial(rng)
            elif rng.random() < 0.10:
                mensaje = rng.choice(NO_MUSICOS)
            else:
                mensaje = rng.choice(CONTINUACIONES + [_frase_inicial(rng)])
                if mensaje == anterior:
                    mensaje = rng.choice(CONTINUACIONES)
            anterior = mensaje
            turnos.append({"sesion": sesion, "indice": indice + 1,
                           "mensaje": mensaje[:500]})
    return turnos


def evento_de(respuesta: dict, turno: dict, ms_cliente: float, estado: int) -> dict:
    """Reconstruye el evento del servidor a partir de la respuesta pública."""
    ev = respuesta.get("evaluacion") or {}
    llm = respuesta.get("llm") or {}
    tarjetas = respuesta.get("module3_reranked") or []
    ranking = [{k: c.get(k) for k in CAMPOS_TARJETA} for c in tarjetas]
    return {
        "id": ev.get("id") or f"{turno['sesion']}-{turno['indice']}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": turno["sesion"],
        "turno": ev.get("turno") or turno["indice"],
        "mensaje": turno["mensaje"],
        "query_en": respuesta.get("query_en"),
        "tipo_turno": ev.get("tipo_turno"),
        "respuesta": respuesta.get("response") or "",
        "latencies_ms": respuesta.get("latencies_ms") or {},
        "calidad": {
            "perfil": ev.get("perfil") or "",
            "perfil_heredado": bool(ev.get("perfil_heredado")),
            "cobertura_m3": ev.get("cobertura_m3"),
            "metadata_coverage": ev.get("metadata_coverage"),
            "emergentes": ev.get("emergentes"),
            "reconocidos": ev.get("reconocidos"),
            "artistas_distintos": ev.get("artistas_distintos"),
            "tipo_turno": ev.get("tipo_turno"),
            "intencion": llm.get("intencion"),
            "llm_proveedor": llm.get("proveedor"),
            "llm_rechazado": bool(llm.get("rechazada")),
        },
        "ranking": ranking,
        "destacadas": respuesta.get("destacadas"),
        "pool_m2": [c.get("id") for c in (respuesta.get("module2_retrieval") or [])],
        "ms_cliente": ms_cliente,
        "http_status": estado,
        "origen": "cliente_evaluacion",
    }


def llamar(url: str, sesion: str, mensaje: str, timeout: float) -> tuple[int, dict, float]:
    cuerpo = json.dumps({"session_id": sesion, "message": mensaje}).encode("utf-8")
    req = request.Request(url, data=cuerpo, headers={"Content-Type": "application/json"})
    inicio = time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            bruto = resp.read().decode("utf-8", "replace")
            estado, datos = resp.status, json.loads(bruto)
    except error.HTTPError as exc:
        detalle = exc.read().decode("utf-8", "replace")[:300]
        return exc.code, {"error": detalle}, round((time.perf_counter() - inicio) * 1000, 1)
    except Exception as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}, round(
            (time.perf_counter() - inicio) * 1000, 1)
    return estado, datos, round((time.perf_counter() - inicio) * 1000, 1)


def resumir(eventos: list[dict], fallos: list[dict], desde: float) -> dict:
    ok = [e for e in eventos if e.get("ranking")]
    lat = [e["ms_cliente"] for e in ok]
    serv = [(e.get("latencies_ms") or {}).get("total") for e in ok]
    serv = [s for s in serv if s]
    tarjetas = [c for e in ok for c in e["ranking"]]
    visibles = [c for e in ok for c in e["ranking"][:int(e.get("destacadas") or 3)]]
    n = len(tarjetas) or 1
    perfiles = [e for e in ok if (e["calidad"].get("perfil") or "sin perfil") != "sin perfil"]
    desvios = [c["desvio_animo"] for c in tarjetas if c.get("desvio_animo") is not None]
    por_sesion: dict[str, int] = {}
    for e in ok:
        por_sesion[e["session_id"]] = por_sesion.get(e["session_id"], 0) + 1
    return {
        "generado": datetime.now(timezone.utc).isoformat(),
        "turnos_enviados": len(eventos) + len(fallos),
        "turnos_con_ranking": len(ok),
        "turnos_fallidos": len(fallos),
        "sesiones": len(por_sesion),
        "turnos_por_sesion": round(statistics.mean(por_sesion.values()), 2) if por_sesion else 0,
        "duracion_min": round((time.time() - desde) / 60, 1),
        "turnos_por_minuto": round((len(eventos) + len(fallos)) / max((time.time() - desde) / 60, 0.001), 2),
        "turnos_con_perfil": len(perfiles),
        "pct_turnos_juzgables": round(100 * len(perfiles) / len(ok), 1) if ok else 0,
        "latencia_cliente_ms": {"promedio": round(statistics.mean(lat), 1) if lat else 0,
                                "p50": percentil(lat, 0.5), "p90": percentil(lat, 0.9),
                                "p99": percentil(lat, 0.99)},
        "latencia_servidor_ms": {"promedio": round(statistics.mean(serv), 1) if serv else 0,
                                 "p50": percentil(serv, 0.5), "p90": percentil(serv, 0.9)},
        "tarjetas_internas": len(tarjetas),
        "tarjetas_visibles": len(visibles),
        "emergentes_pct": round(100 * sum(1 for c in tarjetas if c.get("emergente")) / n, 1),
        "reconocidos_pct": round(100 * sum(1 for c in tarjetas if c.get("reconocido")) / n, 1),
        "con_clase_m3_pct": round(100 * sum(1 for c in tarjetas if c.get("intent_conocida")) / n, 2),
        "cumple_genero_pct": round(100 * sum(1 for c in tarjetas if c.get("cumple_genero")) / n, 1),
        "desvio_animo_promedio": round(statistics.mean(desvios), 3) if desvios else None,
        "artistas_distintos_promedio": round(statistics.mean(
            [e["calidad"].get("artistas_distintos") or 0 for e in ok]), 2) if ok else 0,
        "voz_llm": sum(1 for e in ok if (e["calidad"].get("llm_proveedor") or "") not in ("", "determinista")),
        "voz_determinista": sum(1 for e in ok if (e["calidad"].get("llm_proveedor") or "") in ("", "determinista")),
        "rechazos_llm": sum(1 for e in ok if e["calidad"].get("llm_rechazado")),
        "intencion_llm": sum(1 for e in ok if e["calidad"].get("intencion") == "llm"),
        "intencion_heuristica": sum(1 for e in ok if e["calidad"].get("intencion") == "heuristica"),
        "cobertura_m3_promedio_pct": round(100 * statistics.mean(
            [e["calidad"].get("cobertura_m3") or 0 for e in ok]), 1) if ok else 0,
        "caidas_http": {str(f["http_status"]): sum(1 for x in fallos if x["http_status"] == f["http_status"])
                        for f in fallos},
        "errores": fallos[:20],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Turnos de evaluación con ranking completo.")
    ap.add_argument("--total", type=int, default=330)
    ap.add_argument("--url", default=URL_DEMO)
    ap.add_argument("--rpm", type=float, default=9.0,
                    help="tope de turnos por minuto; el servidor corta en 12 por IP")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--semilla", type=int, default=20261116)
    ap.add_argument("--salida", default=str(RAIZ / "build" / "eva"))
    args = ap.parse_args()

    carpeta = Path(args.salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%y%m%d-%H%M")
    ruta_jsonl = carpeta / f"turnos_{marca}.jsonl"
    ruta_fallos = carpeta / f"fallos_{marca}.jsonl"
    ruta_resumen = carpeta / f"resumen_{marca}.json"
    stop = carpeta / "STOP"
    if stop.exists():
        stop.unlink()

    turnos = construir_turnos(args.total, args.semilla, marca)
    intervalo = 60.0 / max(args.rpm, 0.1)
    print(f"{len(turnos)} turnos · {args.rpm}/min · {ruta_jsonl}", flush=True)

    eventos: list[dict] = []
    fallos: list[dict] = []
    inicio = time.time()
    siguiente = inicio
    with open(ruta_jsonl, "a", encoding="utf-8") as f, \
            open(ruta_fallos, "a", encoding="utf-8") as g:
        for i, turno in enumerate(turnos, 1):
            if stop.exists():
                print("STOP detectado: se cierra la corrida.", flush=True)
                break
            espera = siguiente - time.time()
            if espera > 0:
                time.sleep(espera)
            siguiente = time.time() + intervalo

            estado, datos, ms = llamar(args.url, turno["sesion"], turno["mensaje"], args.timeout)
            # 429 es el limitador por IP: se espera y se reintenta el MISMO turno,
            # sin tocar cabeceras de proxy ni repartir el tráfico entre orígenes.
            intentos = 0
            while estado == 429 and intentos < 4:
                intentos += 1
                time.sleep(20 * intentos)
                siguiente = time.time() + intervalo
                estado, datos, ms = llamar(args.url, turno["sesion"], turno["mensaje"], args.timeout)

            if estado == 200 and datos.get("response"):
                evento = evento_de(datos, turno, ms, estado)
                eventos.append(evento)
                f.write(json.dumps(evento, ensure_ascii=False) + "\n")
                f.flush()
            else:
                fallo = {"timestamp": datetime.now(timezone.utc).isoformat(),
                         "sesion": turno["sesion"], "indice": turno["indice"],
                         "mensaje": turno["mensaje"], "http_status": estado,
                         "ms_cliente": ms, "error": datos.get("error")}
                fallos.append(fallo)
                g.write(json.dumps(fallo, ensure_ascii=False) + "\n")
                g.flush()

            if i % 10 == 0 or i == len(turnos):
                transcurrido = (time.time() - inicio) / 60
                print(f"  {i}/{len(turnos)} · ok={len(eventos)} fallos={len(fallos)} "
                      f"· {transcurrido:.1f} min · último {ms:.0f} ms", flush=True)

    resumen = resumir(eventos, fallos, inicio)
    resumen["archivo_turnos"] = str(ruta_jsonl)
    ruta_resumen.write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2), flush=True)
    return 0 if len(fallos) <= max(1, int(0.05 * (len(eventos) + len(fallos)))) else 1


if __name__ == "__main__":
    raise SystemExit(main())