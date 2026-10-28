# app.py - EchoPulse AI Orchestrator (FLUJO CORREGIDO)
# Módulos: Módulo 2 (Retrieval) → Módulo 3 (Re-ranking)
# Voz: Qwen gratis vía llm_client.py (Ollama local / endpoint compatible OpenAI)

import json
import sys
import time
import os
import re
import math
import pickle
import urllib.parse
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
from sklearn.preprocessing import MinMaxScaler
import torch.serialization
from datetime import datetime
from collections import defaultdict
from threading import Lock
import logging

try:
    import conversacion
    import limite
    import perfiles
    import rerank
    from llm_client import ClienteLLM
except ImportError as exc:  # pragma: no cover - arranque mal configurado
    raise SystemExit(
        f"❌ Faltan módulos del agente ({exc}). Ejecuta app.py desde la carpeta "
        "echopulse_llm_orquestator/ (necesita llm_client.py, conversacion.py, "
        "perfiles.py, rerank.py y limite.py)."
    )

# =====================================================================
# CONFIGURACIÓN DE LOGGING Y MÉTRICAS
# =====================================================================
# BASE_DIR/LOGS_DIR van ANTES del handler: 'logs/metrics.log' relativo al cwd
# reventaba el arranque si el directorio todavía no existía (Docker, CI).
BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(LOGS_DIR / "metrics.log", encoding="utf-8", mode="a"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =====================================================================
# FIX PyTorch 2.6+ para cargar objetos sklearn
# =====================================================================
torch.serialization.add_safe_globals([MinMaxScaler])

# =====================================================================
# CONFIGURACIÓN INICIAL
# =====================================================================
# Windows: consolas cp1252 no pueden imprimir emojis (✅/⚠️) → no romper
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except AttributeError:
    pass

load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)
# HF_TOKEN es OPCIONAL: el agente funciona con Ollama local u otro endpoint
# compatible OpenAI. El router de HF solo se usa si la cuenta tiene créditos.
HF_TOKEN = os.getenv("HF_TOKEN")
if not HF_TOKEN or not HF_TOKEN.startswith("hf_"):
    print("ℹ️ Sin HF_TOKEN válido: el router de Hugging Face no se usará (no hace falta).")

# =====================================================================
# 📊 MÉTRICAS: telemetría operativa + insumos de evaluación de la tesis
# =====================================================================
class SimpleMetrics:
    """Dos niveles deliberadamente separados.

    * `get_summary()` → operación (latencia, éxito) y CALIDAD DEL PIPELINE
      (cobertura de metadatos, cobertura del Módulo 3, perfil de ánimo aplicado,
      diversidad, respaldos del LLM). Son medibles hoy, pero NO son precisión de
      recomendación: sin etiquetas no hay Hit Rate ni MRR que valga.
    * `events_file` (JSONL, un evento por turno con el ranking completo, las
      latencias y la respuesta) → material reproducible para calcular
      HR/Recall/Precision/MRR/NDCG en cuanto existan relevancias, ya sean del
      estudio de usuario (`/api/feedback`) o de un dataset etiquetado.

    El JSONL guarda también el texto del usuario y la respuesta del agente: es
    dato de la demo, no anonimizado, y vive en `logs/` (fuera de Git).
    """

    def __init__(self):
        self.counters = defaultdict(int)
        self.timings = defaultdict(list)
        self.errors = []
        self._lock = Lock()
        mes = datetime.now().strftime("%Y-%m")
        self.metrics_file = LOGS_DIR / f"metrics_{mes}.jsonl"
        self.events_file = LOGS_DIR / f"events_{mes}.jsonl"
        self.feedback_file = LOGS_DIR / f"feedback_{mes}.jsonl"

    def timer(self, stage):
        class _Timer:
            def __init__(t_self, outer, name):
                t_self.outer = outer
                t_self.name = name
                t_self.start = None
            def __enter__(t_self):
                t_self.start = time.time()
                return t_self
            def __exit__(t_self, *args):
                elapsed = (time.time() - t_self.start) * 1000
                with t_self.outer._lock:
                    t_self.outer.timings[t_self.name].append(elapsed)
                    t_self.outer.counters[f"{t_self.name}_calls"] += 1
                logger.info(f"📊 [{t_self.name}] {elapsed:.1f}ms")
        return _Timer(self, stage)

    def _acumular(self, c, calidad: dict):
        c["metadata_hits"] += calidad.get("metadata_hits", 0)
        c["metadata_misses"] += calidad.get("metadata_misses", 0)
        if "cobertura_m3" in calidad:
            c["m3_cobertura_sum"] += calidad["cobertura_m3"]
            c["m3_cobertura_n"] += 1
            if not calidad["cobertura_m3"]:
                c["turnos_sin_clase_m3"] += 1
        if calidad.get("perfil"):
            c["turnos_con_perfil"] += 1
        c["emergentes"] += calidad.get("emergentes", 0)
        c["reconocidos"] += calidad.get("reconocidos", 0)
        if "artistas_distintos" in calidad:
            c["artistas_distintos_sum"] += calidad["artistas_distintos"]
            c["artistas_distintos_n"] += 1
        c["repetidas_filtras"] += calidad.get("repetidas", 0)

    def record_query(self, success=True, error=None, metadata_hits=0,
                     metadata_misses=0, stages=None, calidad=None, evento=None):
        calidad = dict(calidad or {})
        calidad.setdefault("metadata_hits", metadata_hits)
        calidad.setdefault("metadata_misses", metadata_misses)
        with self._lock:
            c = self.counters
            c["total_queries"] += 1
            if success:
                c["successful_queries"] += 1
            else:
                c["failed_queries"] += 1
                self.errors.append({"timestamp": datetime.now().isoformat(), "error": error})
            self._acumular(c, calidad)
            proveedor = calidad.get("llm_proveedor") or "determinista"
            if proveedor == "determinista":
                c["respuestas_deterministas"] += 1
            else:
                c["respuestas_llm"] += 1
                if calidad.get("llm_rechazado"):
                    c["respuestas_llm_rechazadas"] += 1
            for nombre, valor in (stages or {}).items():
                self.timings[nombre].append(valor)
                self.timings[nombre] = self.timings[nombre][-500:]
            total_ms = (stages or {}).get("total")
            record = {
                "timestamp": datetime.now().isoformat(),
                "success": success, "error": error,
                "calidad": calidad,
                "latencies_ms": {k: round(v, 1) for k, v in (stages or {}).items()},
                "avg_latency_ms": round(total_ms, 1) if total_ms else 0,
            }
            with open(self.metrics_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            if evento is not None:
                with open(self.events_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(evento, ensure_ascii=False) + "\n")

    def record_feedback(self, dato: dict):
        """Etiqueta de usuario sobre un turno: la única ground truth posible aquí."""
        with self._lock:
            self.counters["feedback_total"] += 1
            self.counters[f"feedback_{dato.get('valor', 'otro')}"] += 1
            with open(self.feedback_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({"timestamp": datetime.now().isoformat(), **dato},
                                   ensure_ascii=False) + "\n")

    def record_bloqueo(self):
        """Turnos rechazados por el límite por IP: telemetría de la demo pública."""
        with self._lock:
            self.counters["consultas_bloqueadas"] += 1

    def _percentil(self, datos, q):
        if not datos:
            return 0
        ordenado = sorted(datos)
        i = min(len(ordenado) - 1, max(0, int(round(q * (len(ordenado) - 1)))))
        return round(ordenado[i], 1)

    def get_summary(self):
        with self._lock:
            c = self.counters
            total = c["total_queries"]
            hits, misses = c["metadata_hits"], c["metadata_misses"]
            lat = self.timings.get("total", [])
            return {
                # --- operación (telemetría, no es precisión de recomendación) ---
                "total_queries": total,
                "success_rate": (c["successful_queries"] / total * 100) if total else 0,
                "avg_latency_ms": round(float(np.mean(lat)), 1) if lat else 0,
                "latency_p50_ms": self._percentil(lat, 0.50),
                "latency_p90_ms": self._percentil(lat, 0.90),
                "latency_p99_ms": self._percentil(lat, 0.99),
                # --- calidad del pipeline ---
                "metadata_coverage": (hits / (hits + misses) * 100) if (hits + misses) else 0,
                "m3_coverage": (c["m3_cobertura_sum"] / c["m3_cobertura_n"] * 100) if c["m3_cobertura_n"] else 0,
                "turnos_sin_clase_m3": c["turnos_sin_clase_m3"],
                "turnos_con_perfil": c["turnos_con_perfil"],
                "artistas_distintos_promedio": (
                    c["artistas_distintos_sum"] / c["artistas_distintos_n"]
                    if c["artistas_distintos_n"] else 0),
                "emergentes_recomendados": c["emergentes"],
                "reconocidos_recomendados": c["reconocidos"],
                "repetidas_filtras": c["repetidas_filtras"],
                "respuestas_llm": c["respuestas_llm"],
                "respuestas_llm_rechazadas": c["respuestas_llm_rechazadas"],
                "respuestas_deterministas": c["respuestas_deterministas"],
                "feedback_total": c["feedback_total"],
                "feedback_gust": c["feedback_gust"],
                "feedback_no_gust": c["feedback_no_gust"],
                "consultas_bloqueadas": c["consultas_bloqueadas"],
                "errores": list(self.errors[-10:]),
                "avisos_evaluacion": (
                    "Hit Rate / MRR / NDCG requieren etiquetas de relevancia: "
                    "se calculan sobre logs/events_*.jsonl + logs/feedback_*.jsonl, "
                    "nunca a partir de estos contadores."
                ),
            }

metrics = SimpleMetrics()

# =====================================================================
# 💬 MEMORIA DE CONVERSACIÓN POR SESIÓN
# =====================================================================
CONVERSACIONES = {}  # {session_id: {"messages": [...], "recomendados": set(), "ts": float}}
MAX_MENSAJES_HISTORIAL = 10
SESION_TTL_SEGUNDOS = 2 * 60 * 60  # 2 horas sin actividad → la sesión expira
MAX_SESIONES = int(os.getenv("MAX_SESIONES", "500"))  # techo de memoria en la VM

def obtener_sesion(session_id: str) -> dict:
    ahora = time.time()
    for sid in [s for s, d in CONVERSACIONES.items() if ahora - d["ts"] > SESION_TTL_SEGUNDOS]:
        del CONVERSACIONES[sid]
    # Demo pública: si alguien abre cientos de sesiones, se liberan las más
    # antiguas antes de crear una nueva (solo pierden el historial de chat).
    while len(CONVERSACIONES) >= MAX_SESIONES:
        mas_vieja = min(CONVERSACIONES.items(), key=lambda kv: kv[1]["ts"])[0]
        del CONVERSACIONES[mas_vieja]
    return CONVERSACIONES.setdefault(session_id, {
        "messages": [],           # turnos reales de chat (role/content)
        "recomendados": set(),    # IDs ya ofrecidos: el retrieval no los repite
        "ts": ahora,
        "turnos": 0,              # contador para variar las respuestas
        "ultima_query_en": "",    # vibra actual, para "otras parecidas"
        "perfil_pedido": {},      # género/ánimo del último turno, para heredarlos
        "ultimos_nombres": [],    # últimas canciones, para retomarlas al hablar
        "ultimo_turno": None,     # id del último evento: lo que etiqueta /api/feedback
        "etiquetables": {},       # evento_id → turno/consulta reales del feedback
    })

# =====================================================================
# 🎯 UTILIDADES: Cache de Metadatos + Enlaces Reales
# =====================================================================
POP_RECONOCIDO = int(os.getenv("POP_RECONOCIDO", "60"))  # umbral de popularidad Spotify
# Fuerza del castigo por ánimo (0 = desactivado, 1 = canción opuesta pierde todo).
ANIMO_FILTRO = float(os.getenv("ANIMO_FILTRO", "0.60"))
# Idem para el género pedido: las etiquetas del catálogo son ruidosas, así que se
# castiga menos que el ánimo para no quedarse sin pool cuando el género escasea.
GENERO_FILTRO = float(os.getenv("GENERO_FILTRO", "0.50"))

def _vacio(x) -> bool:
    """Sin valor útil: None, vacío, 'Unknown' o el 'nan' que sale de un NaN en parquet."""
    return not x or str(x).strip().lower() in ("unknown", "none", "nan", "null", "?", "-")

def _nombre_real(candidato: dict) -> bool:
    """True si la candidata tiene un título que se pueda mostrar al usuario.

    Las filas de la tabla maestra sin `track_title` daban tarjetas que la UI
    tenía que rotular como "Canción recomendada" (en la demo se veía como un
    fallo del recomendador cuando era un hueco del catálogo).
    """
    return not _vacio(candidato.get("track_name"))


def _genero_principal(candidato: dict) -> str:
    """Género mostrable de una candidata: la etiqueta canónica, no el texto crudo.

    `generos` (conjunto canónico de las tres columnas del catálogo) ya viene
    ordenado con el género pedido primero, así que "rock · blues" gana a un
    `genre_lyr` suelto que diga solo "blues" para una canción de rock.
    """
    for etiqueta in candidato.get("generos") or []:
        if not _vacio(etiqueta):
            return str(etiqueta).strip()
    return "" if _vacio(candidato.get("genre")) else str(candidato["genre"]).strip()

def _norm_join_key(s) -> str:
    """Clave normalizada (artista, título) para unir tablas por nombre."""
    s = re.sub(r"[^a-z0-9 ]", "", str(s).lower())
    return re.sub(r"\s+", " ", s).strip()

def _a_popularidad_int(x):
    try: return int(float(x))
    except (TypeError, ValueError): return None

SONG_METADATA_CACHE = {}

def cargar_metadata_cache(models_dir):
    metadata_path = Path(models_dir) / "song_metadata.json"
    if metadata_path.exists():
        with open(metadata_path, "r", encoding="utf-8") as f:
            global SONG_METADATA_CACHE
            SONG_METADATA_CACHE = json.load(f)
        print(f"✅ Cache de metadatos cargado: {len(SONG_METADATA_CACHE)} canciones")
    else:
        print("⚠️ No se encontró song_metadata.json. Usando fallback 'Unknown'.")

def obtener_metadata(song_id: str) -> dict:
    return SONG_METADATA_CACHE.get(song_id, {"track_name": "Unknown", "artist_name": "Unknown", "genre": "Unknown"})

def generar_enlaces_reales(song_id: str, track="", artist="", genre="") -> dict:
    """Enlaces construidos con los nombres REALES de la canción (tras el merge).

    Antes se generaban con el cache parcial de metadatos: para ~10 mil
    canciones el artista era "Unknown" y la búsqueda de YouTube degeneraba
    en "rock music official" — la canción mostrada nunca aparecía."""
    track = "" if _vacio(track) else str(track).strip()
    artist = "" if _vacio(artist) else str(artist).strip()
    genre = "" if _vacio(genre) else str(genre).strip()

    is_spotify_id = bool(song_id and len(song_id) == 22 and song_id.isalnum() and not song_id.startswith("TR"))

    if is_spotify_id:
        spotify_url = f"https://open.spotify.com/track/{song_id}"
    else:
        query = f"{artist} {track}".strip()
        spotify_url = f"https://open.spotify.com/search/{urllib.parse.quote(query)}" if query else "https://open.spotify.com"

    if artist and track:
        # Sin sufijo "official audio": deja fuera uploads de artistas no famosos
        yt_query = f"{artist} {track}"
    elif track:
        yt_query = track
    elif genre:
        yt_query = f"{genre} music"
    elif artist:
        yt_query = f"{artist} music"
    else:
        yt_query = "music"

    youtube_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(yt_query.strip())}"

    return {"spotify_url": spotify_url, "youtube_url": youtube_url, "youtube_query": yt_query.strip()}

def enriquecer_candidato(candidato: dict) -> dict:
    song_id = candidato.get("id", "")
    metadata = obtener_metadata(song_id)
    # 1) Merge primero: el candidato manda; el metadata solo rellena campos
    #    vacíos/Unknown y nunca pisa un nombre real con "Unknown"
    merged = {**metadata, **candidato}
    for key in ("track_name", "artist_name", "genre"):
        if _vacio(merged.get(key)) and not _vacio(metadata.get(key)):
            merged[key] = metadata[key]
    merged["sin_nombre"] = not _nombre_real(merged)
    # 2) Enlaces DESPUÉS del merge: YouTube busca por los nombres reales de la
    #    recomendación, también para artistas emergentes sin biografía en cache
    enlaces = generar_enlaces_reales(
        song_id,
        track=merged.get("track_name"),
        artist=merged.get("artist_name"),
        genre=_genero_principal(merged),
    )
    return {**merged, **enlaces}

# =====================================================================
# 🌐 LLM CONVERSACIONAL — Qwen gratis, multi-proveedor
# =====================================================================
# El router de Hugging Face ya no sirve Qwen gratis: sin créditos responde
# 402 "You have no remaining credits". ClienteLLM (llm_client.py) prueba en
# orden los backends configurados (endpoint propio → Ollama local con Qwen →
# router HF) y se salta los que están caídos, sin reintentar errores fatales.
llm = ClienteLLM(log=print)
# Ping de arranque en segundo plano: deja Qwen local caliente y descubre ya
# (no en el primer mensaje) que el router de HF responde 402 sin créditos.
llm.diagnosticar()

# Palabras que ya vienen en inglés y sirven tal cual como keywords de retrieval
KEYWORDS_EN_DIRECTAS = {
    "piano", "rain", "night", "dance", "danceable", "love", "sad", "party",
    "rock", "pop", "jazz", "folk", "metal", "rap", "guitar", "acoustic",
    "summer", "winter", "soul", "indie", "chill", "lofi", "blues", "country",
}

# Palabras que el modelo puede colar al inicio de las keywords y no son keywords
_RUIDO_KEYWORDS = {
    "keywords", "keyword", "intencion", "intención", "intent", "respuesta",
    "answer", "output", "user", "usuario", "english", "ingles", "inglés",
    "solo", "only", "result", "resultado",
}


def keywords_heuristicas(mensaje: str) -> str:
    """Keywords EN sin LLM: diccionario de tonos + palabras inglesas directas."""
    _, _, keywords = conversacion.detectar_tono(mensaje)
    if keywords != "chill music":
        return keywords
    palabras = re.sub(r"[^a-zA-Z0-9\s]", "", mensaje.lower()).split()
    directas = [p for p in palabras if p in KEYWORDS_EN_DIRECTAS]
    return ", ".join(dict.fromkeys(directas))[:80] if directas else "chill music"


def validar_keywords(texto: str) -> str | None:
    """Limpia ruido y delega la validación estricta en conversacion.py."""
    if not texto:
        return None
    limpio = re.sub(r"[^a-zA-Z0-9,\s-]", " ", texto)
    for ruido in _RUIDO_KEYWORDS:
        limpio = re.sub(rf"\b{re.escape(ruido)}\b\s*", "", limpio, flags=re.IGNORECASE)
    return conversacion.validar_keywords_en(limpio)


def respuesta_sin_llm(candidatos, mensaje_usuario, sesion) -> str:
    """Respaldo conversacional determinista (conversacion.py)."""
    return conversacion.respuesta_determinista(mensaje_usuario, candidatos, sesion)


# =====================================================================
# ⚖️ MÓDULO 2: MST_MR_Transformer - RETRIEVAL PRINCIPAL (CORREGIDO)
# =====================================================================
class MST_MR_Transformer(nn.Module):
    def __init__(self, vocab_size, n_tech=26, d_model=512, nhead=8, num_layers=6, max_len=151):
        super().__init__()
        self.lyric_emb = nn.Embedding(vocab_size, d_model, padding_idx=0)
        self.pos_encoding = nn.Parameter(torch.zeros(1, max_len, d_model))
        self.tech_projection = nn.Sequential(nn.Linear(n_tech, 256), nn.GELU(), nn.Linear(256, d_model))
        self.cross_attn = nn.MultiheadAttention(d_model, nhead, batch_first=True)
        self.norm_fusion = nn.LayerNorm(d_model)
        decoder_layer = nn.TransformerDecoderLayer(d_model, nhead, batch_first=True)
        self.decoder = nn.TransformerDecoder(decoder_layer, num_layers=num_layers)
        self.fc_out = nn.Linear(d_model, d_model)
        
    def forward(self, lyrics_idx, tech_features):
        x_lyric = self.lyric_emb(lyrics_idx) + self.pos_encoding[:, :lyrics_idx.size(1), :]
        x_tech = self.tech_projection(tech_features).unsqueeze(1)
        attn_out, _ = self.cross_attn(x_lyric, x_tech, x_tech)
        memory = self.norm_fusion(attn_out + x_lyric)
        dec_out = self.decoder(x_lyric, memory)
        return self.fc_out(torch.mean(dec_out, dim=1))

class Module2MasterTable:
    def __init__(self, models_dir, data_dir=None):
        self.path = Path(models_dir) / "tabla_maestra"
        self.data_dir = Path(data_dir) if data_dir else Path(models_dir).parent.parent / "tabla_maestra" / "train"
        self.model = None
        self.vocab = None
        self.scaler = None
        self.df_ref = None
        self.song_embeddings = None
        self.lyric_word_sets = None
        self.song_ids = []        # ID por fila (para exclusión de sesión y diversidad)
        self.artist_names = []    # Artista por fila (para diversidad O(1))
        self.track_names = []     # Título por fila (para join de popularidad)
        self.pop_by_id = []       # Popularidad Spotify por fila (None si se desconoce)
        self.pop_by_key = {}      # Popularidad por (artista, título) normalizados
        self.pop_by_artista = {}  # Popularidad MÁXIMA del artista (índice de fama)
        self.pop_artista_by_id = []  # Popularidad del artista por fila
        self.is_classic = []      # Flag isClassic de WASABI por fila
        self.genero_terms = []    # Términos de género por fila (perfil de búsqueda)
        self.feat_nombre = []     # Rasgos de ánimo que trae el catálogo
        self.feat_cuanto = None   # Cuantiles [0,1] de esos rasgos, por fila
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.t_col = self.a_col = self.l_col = None
        self._load()
        
    def _load(self):
        print(f"🔌 Cargando Módulo 2 (MST_MR - Retrieval) en {self.device}...")
        checkpoint = torch.load(self.path / "mst_mr_final.pth", map_location=self.device, weights_only=False)
        self.vocab = checkpoint["vocab"]
        self.scaler = checkpoint.get("scaler")
        self.model = MST_MR_Transformer(vocab_size=len(self.vocab)).to(self.device)
        self.model.load_state_dict(checkpoint["model"])
        self.model.eval()
        
        # Cargar datos de referencia
        parquet_files = list(Path(self.data_dir).rglob("*.parquet"))
        if parquet_files:
            self.df_ref = pd.read_parquet(parquet_files[0])
            self.t_col = next((c for c in self.df_ref.columns if 'track' in c.lower() or 'title' in c.lower()), 'track_name')
            self.a_col = next((c for c in self.df_ref.columns if 'artist' in c.lower()), 'artist_name')
            self.l_col = 'lyrics_cleaned' if 'lyrics_cleaned' in self.df_ref.columns else 'lyrics'
            
            # Cargar embeddings pre-computados o generar placeholder
            embeddings_path = self.path / "embeddings.pt"
            if embeddings_path.exists():
                self.song_embeddings = torch.load(embeddings_path, map_location=self.device)
            else:
                # Fallback: embeddings aleatorios deterministas por índice
                self.song_embeddings = torch.randn(len(self.df_ref), 512, device=self.device)
                print("⚠️ Módulo 2: embeddings.pt NO encontrado — se usan embeddings ALEATORIOS.")
                print("   ⚠️ La similitud neuronal NO será fiable. Ejecuta precompute_embeddings.py.")
            
            self.lyric_word_sets = [set(str(l).split()) for l in self.df_ref[self.l_col].fillna("")]

            # IDs y artistas/títulos por fila: exclusión de sesión y diversidad en O(1)
            id_series = self.df_ref.get("id")
            if (id_series is None) or id_series.isna().all():
                id_series = self.df_ref.get("msd_id")
            self.song_ids = ([str(v) for v in id_series] if id_series is not None
                             else [f"unknown_{i}" for i in range(len(self.df_ref))])
            self.artist_names = ([str(v) for v in self.df_ref[self.a_col]] if self.a_col in self.df_ref.columns
                                 else ["Unknown"] * len(self.df_ref))
            self.track_names = [str(v) for v in self.df_ref[self.t_col]] if self.t_col in self.df_ref.columns else [""] * len(self.df_ref)

            # 🕯️ Señal de "artista reconocido": popularidad Spotify del cache
            # (por ID o por artista+título normalizado) + flag isClassic de WASABI.
            # Lo que no tiene ninguna de las dos señales → artista emergente.
            self.pop_by_key = {}
            for _md in SONG_METADATA_CACHE.values():
                if not isinstance(_md, dict): continue
                _a, _t = _md.get("artist_name"), _md.get("track_name")
                if _a in (None, "", "Unknown") or _t in (None, "", "Unknown"): continue
                _p = _a_popularidad_int(_md.get("popularity"))
                if _p is not None:
                    self.pop_by_key[(_norm_join_key(_a), _norm_join_key(_t))] = _p

            # 📊 Índice de fama (scripts/build_fame_index.py): popularity Spotify
            # por canción (artista,título) y máx. popularity por ARTISTA desde
            # tracks.csv (~590k tracks). La señal a nivel de ARTISTA corrige los
            # falsos negativos de fama por diferencias de título.
            self.pop_by_artista = {}
            _fame_path = BASE_DIR / "models" / "fame_index.parquet"
            if _fame_path.exists():
                try:
                    _fame = pd.read_parquet(_fame_path)
                    for _t, _a, _p in zip(_fame["tipo"], _fame["artista_n"], _fame["pop"]):
                        if _t == "artista":
                            self.pop_by_artista[_a] = int(_p)
                        else:
                            self.pop_by_key.setdefault((_a, _t), int(_p))
                    print(f"📊 Índice de fama cargado: {len(self.pop_by_artista):,} artistas | "
                          f"{sum(1 for k in self.pop_by_key) :,} claves (artista,título)")
                except Exception as e:
                    print(f"⚠️ No se pudo cargar fame_index.parquet ({e}); genera con scripts/build_fame_index.py")
            else:
                print("⚠️ Sin fame_index.parquet: señal de fama reducida. Genera con scripts/build_fame_index.py")

            self.pop_by_id = [None] * len(self.song_ids)
            self.pop_artista_by_id = [None] * len(self.song_ids)
            for i, _sid in enumerate(self.song_ids):
                p = _a_popularidad_int(SONG_METADATA_CACHE.get(_sid, {}).get("popularity"))
                _na, _nt = _norm_join_key(self.artist_names[i]), _norm_join_key(self.track_names[i])
                if p is None:
                    p = self.pop_by_key.get((_na, _nt))
                self.pop_by_id[i] = p
                self.pop_artista_by_id[i] = self.pop_by_artista.get(_na)
            if "isClassic" in self.df_ref.columns:
                self.is_classic = [str(v).strip().lower() == "true" for v in self.df_ref["isClassic"]]
            else:
                self.is_classic = [False] * len(self.df_ref)

            # 🎚️ Perfil de género + ánimo por fila (ver perfiles.py). El retrieval
            # solo usaba embeddings líricos y Jaccard de letras: ninguna de las dos
            # compara el MOOD pedido con el mood de la canción, así que "algo
            # tranquilo" podía salir en hard rock. Los rasgos se guardan como
            # cuantiles porque están muy sesgados (sadness: mediana 0.03, p75 0.28).
            def _texto(nombre):
                serie = self.df_ref.get(nombre)
                return serie.fillna("").astype(str) if serie is not None else ""
            mezcla = (_texto("genre_lyr") + " | " + _texto("genre_was") + " | " + _texto("album_genre"))
            self.genero_terms = [perfiles.canonicos(g) for g in mezcla]
            bloques, nombres = [], []
            for rasgo in perfiles.FEATURES:
                serie = self.df_ref.get(rasgo)
                if serie is None:
                    continue
                valores = pd.to_numeric(serie, errors="coerce")
                if valores.notna().sum() < 2:
                    continue
                nombres.append(rasgo)
                bloques.append(valores.fillna(valores.median()).to_numpy(dtype="float64"))
            self.feat_nombre = nombres
            self.feat_cuanto = (
                perfiles.cuantiles(np.column_stack(bloques)) if nombres and bloques else None
            )
            print(f"✅ Módulo 2 listo | Canciones: {len(self.df_ref)} | Vocab: {len(self.vocab)} | "
                  f"con popularidad: {sum(1 for p in self.pop_by_id if p is not None)} | "
                  f"con fama de artista: {sum(1 for p in self.pop_artista_by_id if p is not None)} | "
                  f"clásicos: {sum(self.is_classic)} | perfil: {len(nombres)} rasgos "
                  f"({', '.join(nombres) or 'ninguno'})")
        else:
            print("⚠️ Módulo 2: Sin datos de referencia. Usando fallback.")
    
    def tokenize(self, text, max_len=151):
        # Mismo fallback de prefijos que precompute_embeddings.py, para que la
        # consulta viva en el mismo espacio de tokens que los embeddings:
        words = re.sub(r"[^a-zA-Z0-9\s]", "", str(text).lower()).split()
        tokens = []
        for w in words[:max_len]:
            if w in self.vocab:
                tokens.append(self.vocab[w])
            else:
                matched = False
                for pl in (5, 4, 3):
                    if len(w) > pl and w[:pl] in self.vocab:
                        tokens.append(self.vocab[w[:pl]])
                        matched = True
                        break
                if not matched:
                    tokens.append(1)  # <UNK>
        tokens += [0] * (max_len - len(tokens))
        return torch.tensor([tokens], device=self.device)

    def tech_neutral_vector(self):
        """Vector técnico "canción sin datos": mismas convenciones que el
        pre-cómputo de embeddings (relleno 0.5 + escala), no ceros crudos."""
        if self.scaler is not None:
            try:
                tech_vals = np.full((1, 26), 0.5)
                return torch.tensor(self.scaler.transform(tech_vals), dtype=torch.float, device=self.device)
            except Exception as e:
                print(f"⚠️ Módulo 2: scaler fallback a ceros: {e}")
        return torch.zeros(1, 26, device=self.device)

    def retrieve_top10(self, user_query_en, k=10, exclude=None, diag=None, heredar=None):
        """🔍 RETRIEVAL PRINCIPAL: Tabla Maestra por similitud lírica + léxica + perfil.

        exclude: IDs ya recomendados en la sesión. Se apartan ANTES del top-k,
        de modo que siempre se devuelven k canciones nuevas cuando quedan
        disponibles.
        diag: dict opcional que el llamador pasa para recibir qué señales se
        aplicaron (cobertura del perfil, componentes activos). Es para las
        métricas de la tesis: sin eso no se puede explicar un mal ranking.
        heredar: (géneros, ánimo) del turno anterior, solo en turnos de
        continuación. Sin ello "dame más de esa energía" se queda sin género y
        el cupo de emergentes devuelve jazz después de una tanda de rock.
        """
        if self.df_ref is None or len(self.df_ref) == 0:
            # Fallback: retornar IDs dummy si no hay datos
            return [{"id": f"fallback_{i}", "similarity": 0.5 - i*0.05, "track_name": "Unknown", "artist_name": "Unknown"} for i in range(k)]
        
        tokens = self.tokenize(user_query_en)
        tech_neutral = self.tech_neutral_vector()
        query_set = set(re.sub(r"[^a-zA-Z0-9\s]", "", user_query_en.lower()).split())
        excl = set(exclude) if exclude else set()
        
        with torch.no_grad():
            query_emb = F.normalize(self.model(tokens, tech_neutral), dim=1)
            neural_sim = F.cosine_similarity(query_emb, self.song_embeddings.to(self.device), dim=1)
            
            jaccard_scores = []
            for ws in self.lyric_word_sets:
                union = query_set | ws
                jaccard_scores.append(len(query_set & ws) / len(union) if union else 0.0)
            jaccard_scores = torch.tensor(jaccard_scores, device=self.device)
            
            # Score ponderado: neuronal + léxico + perfil (género/ánimo).
            # Cada componente se normaliza en el pool antes de pesarlo: con
            # consultas cortas por keywords, Jaccard crudo es órdenes de
            # magnitud más pequeño que la similitud neural y no contribuiría.
            # Los pesos se renormalizan sobre los componentes que SÍ tienen
            # señal: una consulta sin mood no castiga a nadie por un perfil vacío.
            neural_sim = torch.nan_to_num(neural_sim, nan=0.0)
            jaccard_scores = torch.nan_to_num(jaccard_scores, nan=0.0)

            def _norm_01(t: torch.Tensor) -> torch.Tensor:
                t_min, t_max = t.min(), t.max()
                if not torch.isfinite(t_max - t_min) or (t_max - t_min).item() < 1e-9:
                    return torch.zeros_like(t)
                return (t - t_min) / (t_max - t_min)

            generos_pedido, animo_pedido = perfiles.perfil_consulta(user_query_en)
            generos_pedido, animo_pedido, perfil_heredado = perfiles.heredar_perfil(
                generos_pedido, animo_pedido, heredar
            )
            perfil_np = perfiles.perfil_vector(
                generos_pedido, animo_pedido, self.genero_terms,
                self.feat_nombre, self.feat_cuanto,
            )
            componentes = [("neural", 0.40, _norm_01(neural_sim)),
                           ("lexico", 0.60, _norm_01(jaccard_scores))]
            if perfil_np is not None:
                perfil = torch.nan_to_num(
                    torch.as_tensor(perfil_np, dtype=torch.float, device=self.device), nan=0.0
                )
                componentes = [("neural", 0.30, _norm_01(neural_sim)),
                               ("lexico", 0.35, _norm_01(jaccard_scores)),
                               ("perfil", 0.35, perfil)]
            # Un componente sin discriminación (normalizado todo a 0) no debe
            # arrastrar el score: se sale y su peso se reparte entre los activos.
            activos = [c for c in componentes if c[2].abs().sum().item() > 0] or componentes[:1]
            total_pesos = sum(peso for _, peso, _ in activos) or 1.0
            score = sum((peso / total_pesos) * v for _, peso, v in activos)

            # Guardabarros de ánimo y género: lo que el usuario pidió explícitamente
            # se impone como castigo multiplicativo, no como una señal más que el
            # blend puede votarse. Con peso 0.35, "tranquilo" devolvía rock y "rock
            # con garra" devolvía blues porque la similitud neural y la letra pesan
            # más que la etiqueta.
            # Los desvíos por fila también se guardan en la candidata: dan una
            # métrica de alineación SIN etiquetas (¿el top-10 cumple lo pedido?).
            filtros: dict[str, torch.Tensor] = {}
            promedios: dict[str, float] = {}
            senales = [
                ("animo_filtro",
                 perfiles.distancia_animo(animo_pedido, self.feat_nombre, self.feat_cuanto),
                 ANIMO_FILTRO),
                ("genero_filtro",
                 perfiles.desvio_genero(generos_pedido, self.genero_terms),
                 GENERO_FILTRO),
            ]
            for nombre, desvio, fuerza in senales:
                if desvio is None:
                    continue
                d = torch.as_tensor(desvio, dtype=torch.float, device=self.device)
                filtros[nombre] = d
                if fuerza > 0:
                    score = score * (1.0 - fuerza * d).clamp(min=0.0)
                promedios[nombre] = round(float(d.mean().item()), 3)
            if diag is not None:
                diag["perfil"] = perfiles.describir_perfil(generos_pedido, animo_pedido)
                diag["componentes"] = [n for n, _, _ in activos] + list(filtros)
                diag["filtros"] = promedios
                # Legible por máquina: el llamador lo guarda en la sesión para
                # heredarlo cuando el usuario solo pide "más de lo mismo".
                diag["generos_pedido"] = sorted(generos_pedido)
                diag["animo_pedido"] = dict(animo_pedido)
                diag["perfil_heredado"] = perfil_heredado

            # Apartar canciones ya recomendadas en la sesión antes del top-k
            if excl and self.song_ids:
                excl_idx = torch.tensor(
                    [i for i, sid in enumerate(self.song_ids) if sid in excl],
                    dtype=torch.long, device=self.device)
                if excl_idx.numel():
                    score[excl_idx] = float("-inf")
            
            k = min(k, len(score))
            top_val, top_idx = torch.topk(score, k)
        
        results = []
        for val, idx in zip(top_val.tolist(), top_idx.tolist()):
            safe_sim = float(val)
            if math.isnan(safe_sim) or math.isinf(safe_sim): continue  # excluidas u datos inválidos
            idx = int(idx)
            row = self.df_ref.iloc[idx]
            # Artista reconocido: popularidad Spotify de la CANCIÓN o del ARTISTA
            # (>= POP_RECONOCIDO), o canción clásica de WASABI. Sin ninguna de
            # las dos señales → emergente (candidato a prioridad del agente).
            pop = self.pop_by_id[idx] if idx < len(self.pop_by_id) else None
            pop_art = self.pop_artista_by_id[idx] if idx < len(self.pop_artista_by_id) else None
            is_c = self.is_classic[idx] if idx < len(self.is_classic) else False
            # Etiquetas canónicas de la fila, con la pedida primero: la ficha puede
            # decir "rock · blues" en vez del único `genre_lyr`, que a veces dice
            # "blues" de una canción que sí es rock según las otras dos columnas.
            generos_fila = sorted(
                self.genero_terms[idx] if idx < len(self.genero_terms) else set(),
                key=lambda nombre: (nombre not in generos_pedido, nombre),
            )
            reconocido = (pop is not None and pop >= POP_RECONOCIDO) \
                or (pop_art is not None and pop_art >= POP_RECONOCIDO) \
                or is_c
            # Alineación con lo pedido, por candidata. Sirve para evaluar sin
            # etiquetas: si el usuario nombró un ánimo, ¿cuánto se desvía esta
            # canción? Si nombró un género, ¿está en sus etiquetas canónicas?
            cumple_genero = None if not generos_pedido else bool(
                set(generos_fila) & generos_pedido
            )
            desvio_animo = None if "animo_filtro" not in filtros else round(
                float(filtros["animo_filtro"][idx]), 3
            )
            results.append({
                "cumple_genero": cumple_genero,
                "desvio_animo": desvio_animo,
                "id": self.song_ids[idx] if idx < len(self.song_ids) else str(row.get("id", row.get("msd_id", f"unknown_{idx}"))),
                "track_name": "" if _vacio(row.get(self.t_col)) else str(row.get(self.t_col)).strip(),
                "artist_name": "" if _vacio(row.get(self.a_col)) else str(row.get(self.a_col)).strip(),
                "genre": "" if _vacio(row.get("genre_lyr", row.get("genre"))) else str(row.get("genre_lyr", row.get("genre"))).strip(),
                "generos": generos_fila,
                "sin_nombre": False,
                "similarity": round(safe_sim, 4),
                "popularity": pop,
                "popularity_artista": pop_art,
                "reconocido": bool(reconocido),
                "emergente": not reconocido,
                "module": "mst_mr_retrieval"
            })
        return results

# =====================================================================
# 🧠 MÓDULO 3: IntentTransformer - RE-RANKING SEMÁNTICO (CORREGIDO)
# =====================================================================
class IntentTransformer(nn.Module):
    def __init__(self, vocab_size, num_songs, d_model=256, n_heads=8, num_layers=4, max_len=512):
        super().__init__()
        self.embed = nn.Embedding(vocab_size, d_model, padding_idx=0)
        self.pos = nn.Parameter(torch.zeros(1, max_len, d_model))
        encoder_layer = nn.TransformerEncoderLayer(d_model, n_heads, dim_feedforward=1024, batch_first=True)
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers)
        self.fc = nn.Linear(d_model, num_songs)
    def forward(self, x):
        x = self.embed(x) + self.pos[:, :x.size(1), :]
        x = self.encoder(x)
        return self.fc(x.mean(dim=1))

class Module3IntentReranker:
    def __init__(self, models_dir):
        self.path = Path(models_dir) / "talkplay"
        self.model = None
        self.vocab = None
        self.idx2song = None
        self.song2idx = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._load()
    def _load(self):
        print(f"🔌 Cargando Módulo 3 (IntentTransformer - Re-ranking) en {self.device}...")
        with open(self.path / "vocab.json", "r", encoding="utf-8") as f: self.vocab = json.load(f)
        with open(self.path / "song_map.pkl", "rb") as f:
            self.song2idx = pickle.load(f)
            self.idx2song = {i: s for s, i in self.song2idx.items()}
        self.model = IntentTransformer(len(self.vocab), len(self.song2idx), max_len=512).to(self.device)
        self.model.load_state_dict(torch.load(self.path / "intent_model.pth", map_location=self.device, weights_only=True))
        self.model.eval()
        print(f"✅ Módulo 3 listo | Clases: {len(self.song2idx)} | Vocab: {len(self.vocab)}")
    
    def tokenize(self, text, max_len=512):
        cleaned = re.sub(r"[^a-zA-Z0-9\s?]", "", str(text).lower())
        tokens = [self.vocab.get(t, self.vocab.get("<UNK>", 1)) for t in cleaned.split()][:max_len]
        tokens += [0] * (max_len - len(tokens))
        return torch.tensor([tokens], device=self.device)
    
    def rerank_candidates(self, candidates: list, user_query_en: str) -> tuple[list, dict]:
        """🎯 RE-RANKING: combina la similitud del Módulo 2 con la intención del 3.

        La intención se normaliza respecto al máximo entre los candidatos que el
        Módulo 3 conoce (sus clases son ~38 mil canciones del set de Talkplay, no
        el subconjunto de la tabla maestra). La aritmética vive en rerank.py para
        poder probarla sin checkpoints; aquí solo se calculan las probabilidades.
        """
        if not candidates: return candidates, {"cobertura_m3": 0.0, "intent_neutra": 0.0,
                                               "candidatas_sin_clase_m3": 0, "m3_aporto_orden": False}
        tokens = self.tokenize(user_query_en)
        with torch.no_grad():
            logits = self.model(tokens)
            probs = F.softmax(logits, dim=1)[0]

        probabilidades = {
            c["id"]: probs[self.song2idx[c["id"]]].item()
            for c in candidates if c.get("id") in self.song2idx
        }
        return rerank.fusionar(candidates, probabilidades)

# =====================================================================
# 🎨 SELECCIÓN DEL TOP N: prioriza emergentes + garantiza reconocidos
# =====================================================================
def seleccionar_candidatos(pool, objetivo=None, max_por_artista=None, minimo_reconocidos=None):
    """Construye el Top N PRIORIZANDO artistas emergentes (sin señal de fama)
    sin dejar de recomendar a los reconocidos.

    - Fase A (cuotas): reserva `cuota_emergente = objetivo - minimo_reconocidos`
      huecos para emergentes y garantiza `minimo_reconocidos` huecos para
      conocidos, tomando de cada grupo los mejores por score y respetando el
      tope por artista.
    - Fase B (huecos libres, si algún grupo faltó en el pool): primero
      emergentes, después conocidos.

    Relaja el tope por artista progresivamente si falta material: cap 2 → 5 → sin tope.
    Config: MAX_POR_ARTISTA, MINIMO_RECONOCIDOS (env).
    """
    if objetivo is None: objetivo = int(os.getenv("TOP_N", "10"))
    if max_por_artista is None: max_por_artista = int(os.getenv("MAX_POR_ARTISTA", "2"))
    if minimo_reconocidos is None: minimo_reconocidos = int(os.getenv("MINIMO_RECONOCIDOS", "3"))
    minimo_reconocidos = max(1, min(minimo_reconocidos, objetivo - 1))
    cuota_eme = objetivo - minimo_reconocidos

    # Sin título no hay tarjeta útil (la UI la rotulaba "Canción recomendada" y
    # el enlace de YouTube caía a una búsqueda genérica): se prefiere lo que
    # sí tiene nombre, salvo que no quede más remedio que mostrar el hueco.
    con_nombre = [c for c in pool if _nombre_real(c)]
    if len(con_nombre) >= objetivo:
        pool = con_nombre

    for cap in (max_por_artista, 5, None):
        elegidos, conteo = [], defaultdict(int)
        usados = set()
        estado = {"n_eme": 0, "n_rec": 0}

        def _cabe(c):
            return cap is None or conteo[(c.get("artist_name") or "Unknown")] < cap

        def _agregar(c):
            elegidos.append(c)
            usados.add(id(c))
            conteo[(c.get("artist_name") or "Unknown")] += 1
            if bool(c.get("emergente", True)): estado["n_eme"] += 1
            else: estado["n_rec"] += 1

        # Fase A: cuotas
        for c in pool:
            if estado["n_eme"] >= cuota_eme and estado["n_rec"] >= minimo_reconocidos: break
            if id(c) in usados or not _cabe(c): continue
            if bool(c.get("emergente", True)):
                if estado["n_eme"] < cuota_eme: _agregar(c)
            else:
                if estado["n_rec"] < minimo_reconocidos: _agregar(c)

        # Fase B: huecos libres — primero emergentes, luego conocidos
        for c in pool:
            if len(elegidos) >= objetivo: break
            if id(c) in usados or not _cabe(c): continue
            if bool(c.get("emergente", True)): _agregar(c)
        for c in pool:
            if len(elegidos) >= objetivo: break
            if id(c) in usados or not _cabe(c): continue
            if not bool(c.get("emergente", True)): _agregar(c)

        if len(elegidos) >= objetivo:
            return elegidos
    return pool[:objetivo]

# =====================================================================
# 🚀 INICIALIZACIÓN DE MÓDULOS (ORDEN CORREGIDO)
# =====================================================================
cargar_metadata_cache(MODELS_DIR)
# En local la tabla maestra vive dos niveles arriba; en Docker/Spaces se
# sobreescribe con TABLA_MAESTRA_DIR para no depender del layout del repo.
module2 = Module2MasterTable(MODELS_DIR, data_dir=os.getenv("TABLA_MAESTRA_DIR"))  # 🔍 Retrieval Principal
module3 = Module3IntentReranker(MODELS_DIR)  # 🎯 Re-ranking Semántico

# =====================================================================
# 🎵 ORQUESTADOR PRINCIPAL (FLUJO CORREGIDO)
# =====================================================================
# auto = el LLM solo afina la intención cuando la heurística no alcanza;
# llm  = siempre pide las keywords al modelo (más calidad, más latencia);
# heuristica = nunca llama al LLM en la Fase 1 (modo demo sin red).
INTENT_MODE = os.getenv("INTENT_MODE", "auto").strip().lower()


def _quiere_llm_para_intencion(tipo_turno: str, heuristicas: str, sesion: dict) -> bool:
    if INTENT_MODE == "llm":
        return True
    if INTENT_MODE == "heuristica":
        return False
    # auto: la heurística ES→EN cubre la mayoría de turnos. El modelo solo entra
    # cuando no hubo ninguna señal de tono y tampoco hay vibe previo que heredar
    # (preguntas y "dame más" se resuelven reutilizando la intención anterior).
    if heuristicas != "chill music":
        return False
    if sesion.get("ultima_query_en"):
        return False
    return tipo_turno in ("pregunta", "musica", "mas_de_lo_mismo")


def procesar_consulta_echopulse(mensaje_usuario, session_id="default"):
    query_start = time.time()
    stage_latencies = {}
    metadata_hits = metadata_misses = 0
    sesion = obtener_sesion(session_id)

    try:
        print(f"\n👤 [{session_id[:8]}] Usuario: {mensaje_usuario}")

        # FASE 1: Refinamiento de intención CONTEXTUAL (conversación + último mensaje)
        print("🔍 Fase 1: Refinando intención con contexto conversacional...")
        t1 = time.time()
        tipo_turno = conversacion.clasificar_mensaje(mensaje_usuario)
        heuristicas = keywords_heuristicas(mensaje_usuario)
        query_en = None
        fuente_intencion = "heuristica"

        if _quiere_llm_para_intencion(tipo_turno, heuristicas, sesion) and llm.activo:
            mensajes_intencion = conversacion.construir_mensajes(
                conversacion.SISTEMA_INTENCION,
                sesion["messages"],
                mensaje_usuario,
                max_turnos=6,
            )
            salida = llm.chat(
                mensajes_intencion, max_tokens=48, temperature=0.1, proposito="intencion"
            )
            if salida:
                propuesta = validar_keywords(salida.texto)
                if propuesta:
                    query_en = propuesta
                    fuente_intencion = salida.proveedor
                    print(
                        f"   🧠 Intención vía {salida.proveedor} "
                        f"({salida.latencia_ms:.0f} ms, {salida.modelo})"
                    )
                else:
                    print(f"   ⚠️ Salida de intención no utilizable: {salida.texto[:80]!r}")

        if not query_en:
            query_en = heuristicas
            if query_en == "chill music" and sesion.get("ultima_query_en"):
                # "otras parecidas", "algo más" → seguir el vibe anterior
                query_en = sesion["ultima_query_en"]
                print("   🔁 Mensaje genérico → se mantiene el vibe anterior")
            else:
                print(f"   🔤 Keywords heurísticas: {query_en}")

        sesion["ultima_query_en"] = query_en
        stage_latencies["translation"] = (time.time() - t1) * 1000
        print(f"   🎯 Keywords (EN): {query_en}")

        # FASE 2: 🔍 Módulo 2 - RETRIEVAL PRINCIPAL (Tabla Maestra)
        print("⚖️ Fase 2: Módulo 2 - Retrieval desde Tabla Maestra...")
        t2 = time.time()
        diagnostico_m2 = {}
        # "dame más", "otras parecidas" → seguir con el género/ánimo del turno
        # anterior; sin eso la tanda nueva se rige solo por el cupo de emergentes.
        heredar = None
        if tipo_turno == "mas_de_lo_mismo":
            previo = sesion.get("perfil_pedido") or {}
            if previo.get("generos") or previo.get("animo"):
                heredar = (previo.get("generos"), previo.get("animo"))
        # No repetir canciones ya recomendadas en esta sesión (exclusión dentro
        # del retrieval garantiza 10 frescas cuando hay disponibles)
        pool_m2 = module2.retrieve_top10(query_en, k=30, exclude=sesion["recomendados"],
                                         diag=diagnostico_m2, heredar=heredar)
        stage_latencies["retrieval"] = (time.time() - t2) * 1000
        sesion["perfil_pedido"] = {
            "generos": diagnostico_m2.get("generos_pedido") or [],
            "animo": diagnostico_m2.get("animo_pedido") or {},
        }
        if diagnostico_m2.get("perfil"):
            heredado = " · heredado" if diagnostico_m2.get("perfil_heredado") else ""
            print(f"   🎚️ Perfil aplicado: {diagnostico_m2['perfil']}{heredado} "
                  f"| señales: {','.join(diagnostico_m2.get('componentes', []))}")

        # Enriquecer ANTES de seleccionar: hay filas de la tabla maestra sin
        # track_title que el cache de metadatos sí puede nombrar. Si se
        # seleccionara primero, esas canciones se colarían como tarjetas sin
        # título ("Canción recomendada") o quedarían fuera sin necesidad.
        pool_enriquecido = [enriquecer_candidato(c) for c in pool_m2]

        frescos = [c for c in pool_enriquecido if c.get("id") not in sesion["recomendados"]]
        candidatos = seleccionar_candidatos(frescos or pool_enriquecido, objetivo=10)
        repetidas = len(pool_enriquecido) - len(frescos)
        n_eme = sum(1 for c in candidatos if c.get("emergente"))
        n_rec = len(candidatos) - n_eme
        sin_nombre = sum(1 for c in candidatos if c.get("sin_nombre"))
        print(f"   📦 Pool: {len(pool_enriquecido)} | nuevas: {len(frescos)} | seleccionadas: {len(candidatos)} "
              f"(emergentes: {n_eme} · reconocidas: {n_rec}) | ya recomendadas (filtradas): {repetidas}")
        if sin_nombre:
            print(f"   ⚠️ {sin_nombre} seleccionada(s) sin título real en el catálogo")

        # FASE 3: 🎯 Módulo 3 - RE-RANKING SEMÁNTICO (Intención)
        print("🧠 Fase 3: Módulo 3 - Re-ranking por intención conversacional...")
        t3 = time.time()
        candidates_m3, diag_m3 = module3.rerank_candidates(candidatos, query_en)
        stage_latencies["reranking"] = (time.time() - t3) * 1000
        print(f"   🎯 Cobertura M3: {diag_m3['cobertura_m3'] * 100:.0f}% del pool "
              f"({diag_m3['candidatas_sin_clase_m3']} sin clase en el re-ranker, "
              f"intención neutra {diag_m3['intent_neutra']})")

        candidates_final = candidates_m3
        sesion["recomendados"].update(c.get("id") for c in candidates_final if c.get("id"))
        for c in candidates_final:
            if not _vacio(c.get("track_name")): metadata_hits += 1
            else: metadata_misses += 1
        print(f"   🔗 Enlaces generados | Meta: {metadata_hits}/{len(candidates_final)}")

        # FASE 4: Respuesta conversacional (historial como turnos reales)
        print("💬 Fase 4: Generando respuesta conversacional con Qwen...")
        t4 = time.time()
        lineas_contexto = []
        for c in candidates_final[:6]:
            nombre = (c.get("track_name") or "").strip() or "Canción sin título"
            artista = (c.get("artist_name") or "").strip() or "artista desconocido"
            genero = _genero_principal(c)
            sufijo = f" [{genero}]" if genero and genero.lower() != "unknown" else ""
            lineas_contexto.append(f"- «{nombre}» — {artista}{sufijo}")
        contexto = "\n".join(lineas_contexto)

        sistema_chat = conversacion.SISTEMA_CHAT
        if contexto:
            sistema_chat += (
                "\n\nCanciones disponibles en este turno (de más a menos afín):\n" + contexto
            )
        if sesion.get("ultimos_nombres"):
            sistema_chat += (
                "\n\nEn el turno anterior sonaron: "
                + ", ".join(sesion["ultimos_nombres"])
                + ". No las vuelvas a mencionar."
            )

        mensajes_chat = conversacion.construir_mensajes(
            sistema_chat, sesion["messages"], mensaje_usuario, max_turnos=8
        )
        salida_chat = llm.chat(
            mensajes_chat,
            max_tokens=int(os.getenv("LLM_MAX_TOKENS_CHAT", "160")),
            temperature=float(os.getenv("LLM_TEMPERATURA_CHAT", "0.7")),
            proposito="respuesta",
        )
        turno = int(sesion.get("turnos", 0))
        llm_rechazado = False
        if salida_chat:
            # Un modelo pequeño puede divagar, enumerar sin contenido o inventar
            # artistas. `validar_respuesta` es la ÚNICA puerta de salida del texto
            # del modelo: si tras la limpieza no queda nada aprovechable se usa el
            # motor determinista. Antes se hacía `texto_llm or salida_chat.texto`,
            # que volvía a inyectar el texto crudo exactamente cuando la limpieza
            # había descartado todo.
            respuesta_final = conversacion.validar_respuesta(
                salida_chat.texto, candidates_final, turno=turno, maximo_frases=5
            )
            modo_respuesta = salida_chat.proveedor
            if respuesta_final is None:
                llm_rechazado = True
                respuesta_final = respuesta_sin_llm(candidates_final, mensaje_usuario, sesion)
                modo_respuesta = "determinista"
                print(f"   ⚠️ Salida del LLM sin contenido aprovechable "
                      f"({salida_chat.texto[:60]!r}) → respaldo determinista")
            else:
                print(f"   🗣️ Respuesta vía {salida_chat.proveedor} "
                      f"({salida_chat.latencia_ms:.0f} ms, {salida_chat.modelo})")
        else:
            respuesta_final = respuesta_sin_llm(candidates_final, mensaje_usuario, sesion)
            modo_respuesta = "determinista"
            print("   ⚠️ Sin LLM disponible → respuesta conversacional determinista")
        stage_latencies["generation"] = (time.time() - t4) * 1000

        # Guardar turno en la memoria de la sesión. Del historial se fuera el
        # refuerzo de plantilla: si queda, el modelo lo copia en los turnos siguientes.
        sesion["messages"].append({"role": "user", "content": mensaje_usuario})
        sesion["messages"].append({
            "role": "assistant",
            "content": conversacion.sin_refuerzos_de_plantilla(respuesta_final),
        })
        sesion["messages"] = sesion["messages"][-2 * MAX_MENSAJES_HISTORIAL:]
        sesion["turnos"] = turno + 1
        nombres = [
            c.get("track_name") for c in candidates_final[:3]
            if not _vacio(c.get("track_name"))
        ]
        sesion["ultimos_nombres"] = nombres
        sesion["ts"] = time.time()

        stage_latencies["total"] = (time.time() - query_start) * 1000

        # 📋 Evaluación de la tesis: un evento por turno, con el ranking completo.
        # Es el insumo de HR/Recall/Precision/MRR/NDCG: esas métricas necesitan
        # etiquetas de relevancia y se calculan offline sobre este JSONL, nunca
        # desde los contadores de operación.
        evento_id = f"{session_id[:8]}-{turno + 1}-{int(query_start * 1000)}"
        sesion["ultimo_turno"] = evento_id
        artistas = {c.get("artist_name") for c in candidates_final if not _vacio(c.get("artist_name"))}
        calidad = {
            "metadata_hits": metadata_hits,
            "metadata_misses": metadata_misses,
            "cobertura_m3": diag_m3["cobertura_m3"],
            "m3_aporto_orden": diag_m3["m3_aporto_orden"],
            "perfil": diagnostico_m2.get("perfil", ""),
            "perfil_heredado": bool(diagnostico_m2.get("perfil_heredado")),
            "componentes_m2": diagnostico_m2.get("componentes", []),
            "emergentes": n_eme,
            "reconocidos": n_rec,
            "artistas_distintos": len(artistas),
            "sin_nombre": sin_nombre,
            "repetidas": repetidas,
            "pool_nuevas": len(frescos),
            "tipo_turno": tipo_turno,
            "intencion": fuente_intencion,
            "llm_proveedor": modo_respuesta,
            "llm_rechazado": llm_rechazado,
        }
        sesion["ultima_calidad"] = calidad
        # /api/feedback puede etiquetar un turno anterior: se guarda el contexto
        # exacto de este evento para no anotar el turno ni la consulta de despues.
        etiquetables = sesion.setdefault("etiquetables", {})
        etiquetables[evento_id] = {
            "turno": turno + 1,
            "query_en": query_en,
            "cobertura_m3": diag_m3["cobertura_m3"],
        }
        while len(etiquetables) > 10:
            etiquetables.pop(next(iter(etiquetables)))
        metrics.record_query(
            success=True, stages=stage_latencies, calidad=calidad,
            evento={
                "id": evento_id,
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "turno": turno + 1,
                "mensaje": mensaje_usuario[:300],
                "query_en": query_en,
                "tipo_turno": tipo_turno,
                "respuesta": respuesta_final,
                "latencies_ms": {k: round(v, 1) for k, v in stage_latencies.items()},
                "calidad": calidad,
                "ranking": [
                    {
                        "rank": c.get("rank"), "id": c.get("id"),
                        "track_name": c.get("track_name"),
                        "artist_name": c.get("artist_name"), "genre": c.get("genre"),
                        "generos": c.get("generos"),
                        "cumple_genero": c.get("cumple_genero"),
                        "desvio_animo": c.get("desvio_animo"),
                        "similarity": c.get("similarity"),
                        "intent_score": c.get("intent_score"),
                        "intent_conocida": c.get("intent_conocida"),
                        "final_score": c.get("final_score"),
                        "emergente": c.get("emergente"),
                        "reconocido": c.get("reconocido"),
                        "popularity": c.get("popularity"),
                    }
                    for c in candidates_final
                ],
            },
        )

        print(f"\n📦 DEBUG - Módulo 2 Top 1 (Retrieval): {pool_m2[0].get('track_name', 'Unknown')}")
        print(f"📦 DEBUG - Módulo 3 Top 1 (Re-ranked): {candidates_final[0].get('track_name', 'Unknown')}")
        print(f"📊 Métricas: {stage_latencies['total']:.0f}ms total | {metadata_hits}/{len(candidates_final)} con metadata | "
              f"cobertura M3 {diag_m3['cobertura_m3'] * 100:.0f}% | voz: {modo_respuesta}")

        return {
            "response": respuesta_final, "query_en": query_en, "session_id": session_id,
            "module2_retrieval": candidatos,  # 🔍 Retrieval entregado al re-ranker
            "module3_reranked": candidates_final,  # 🎯 Resultados finales re-ordenados
            "stages": ["translation", "retrieval_m2", "reranking_m3", "generation"],
            "latencies_ms": {k: round(v, 1) for k, v in stage_latencies.items()},
            "llm": {
                "proveedor": modo_respuesta,
                "intencion": fuente_intencion,
                "etiqueta": llm.descripcion(),
                "rechazada": llm_rechazado,
            },
            "evaluacion": {
                "id": evento_id,
                "cobertura_m3": diag_m3["cobertura_m3"],
                "perfil": diagnostico_m2.get("perfil", ""),
                "perfil_heredado": bool(diagnostico_m2.get("perfil_heredado")),
                "tipo_turno": tipo_turno,
                "metadata_coverage": metadata_hits / len(candidates_final) if candidates_final else 0,
                "emergentes": n_eme,
                "reconocidos": n_rec,
                "artistas_distintos": len(artistas),
            },
            "turno": sesion["turnos"],
        }
    except Exception as e:
        metrics.record_query(success=False, error=str(e))
        logger.error(f"❌ Error en consulta: {e}")
        raise

# =====================================================================
# 🌐 FLASK APP
# =====================================================================
app = Flask(__name__)

# Demo pública: un turno llena los 2 núcleos de la VM durante segundos, así que se
# frena por IP antes de ponerse a calcular. Se usa request.remote_addr y NO
# X-Forwarded-For: sin proxy inverso delante, ese header lo escribe el cliente.
LIMITE_POR_MINUTO = int(os.getenv("LIMITE_POR_MINUTO", "12"))
limitador_chat = limite.LimitadorVentana(LIMITE_POR_MINUTO)
# Los 👍/👎 no gastan el cupo de chat (una tanda admite varios avisos), pero tampoco
# pueden escribir en el log de etiquetas a cualquier ritmo.
limitador_feedback = limite.LimitadorVentana(int(os.getenv("LIMITE_FEEDBACK", "40")))
# Un cuerpo de 16 KB ya es un párrafo absurdo para pedir música; esto corta los
# payloads gigantes antes de que Flask los cargue en memoria.
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

@app.route("/")
def home(): return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def api_chat():
    ip = request.remote_addr or "desconocida"
    if not limitador_chat.permitir(ip):
        metrics.record_bloqueo()
        logger.info(f"🛑 {ip} superó el límite de {LIMITE_POR_MINUTO} turnos por minuto")
        return jsonify({
            "error": ("Demasiadas peticiones seguidas desde tu red. "
                      "Espera un minuto y vuelve a pedir música."),
        }), 429
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "JSON inválido: envía el cuerpo en UTF-8"}), 400
        mensaje = (data.get("message") or "").strip()[:500]
        session_id = (data.get("session_id") or "default").strip()[:64]
        if not mensaje: return jsonify({"error": "Mensaje vacío"}), 400
        resultado = procesar_consulta_echopulse(mensaje, session_id)
        return jsonify(resultado)
    except Exception as e:
        print(f"❌ Error en /api/chat: {e}")
        return jsonify({"error": str(e), "response": "Lo siento, tuve un problema técnico."}), 500

@app.route("/api/chat/reset", methods=["POST"])
def api_chat_reset():
    data = request.json or {}
    session_id = (data.get("session_id") or "default").strip()
    CONVERSACIONES.pop(session_id, None)
    return jsonify({"status": "reset", "session_id": session_id})

@app.route("/api/health")
def health():
    etiqueta = llm.descripcion()
    return jsonify({
        "status": "ok",
        "modules": {
            "llm": etiqueta,
            # compatibilidad con el frontend anterior
            "hf_api": etiqueta,
            "module2_retrieval": "loaded",
            "module3_reranker": "loaded",
        },
    })


def _requiere_admin():
    """Los endpoints que gastan CPU o cambian estado no quedan abiertos al público.

    /api/llm/probar fuerza una inferencia de Qwen por petición y
    /api/llm/revive reescribe la lista de proveedores: en una demo pública con
    la VM abierta 24 h, cualquiera podía tumbar la latencia de los demás. Sin
    ADMIN_TOKEN definido, ambos responden 404 (el demo no los necesita).
    """
    token = os.getenv("ADMIN_TOKEN", "").strip()
    if not token:
        return jsonify({"error": "endpoint de diagnóstico deshabilitado"}), 404
    if (request.headers.get("X-Admin-Token") or "").strip() != token:
        return jsonify({"error": "token de administración requerido"}), 403
    return None


@app.route("/api/llm/status")
def llm_status():
    bloqueado = _requiere_admin()
    if bloqueado:
        return bloqueado
    return jsonify(llm.estado())


@app.route("/api/llm/revive", methods=["POST"])
def llm_revive():
    """Reactiva proveedores marcados como caídos (p. ej. tras recargar créditos)."""
    bloqueado = _requiere_admin()
    if bloqueado:
        return bloqueado
    data = request.json or {}
    llm.revivir(data.get("provider"))
    return jsonify({"status": "revived", "llm": llm.estado()})


@app.route("/api/llm/probar", methods=["POST"])
def llm_probar():
    """Prueba real de la cadena de LLM: responde con quién y en cuánto tiempo."""
    bloqueado = _requiere_admin()
    if bloqueado:
        return bloqueado
    salida = llm.chat(
        [{"role": "user", "content": "Responde solo con la palabra: listo"}],
        max_tokens=8,
        temperature=0.0,
        proposito="diagnostico",
    )
    if not salida:
        return jsonify({"ok": False, "llm": llm.estado()}), 503
    return jsonify({
        "ok": True,
        "respuesta": salida.texto,
        "proveedor": salida.proveedor,
        "modelo": salida.modelo,
        "latencia_ms": round(salida.latencia_ms, 1),
        "llm": llm.estado(),
    })


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    """📋 Etiqueta de relevancia del usuario sobre el turno que acaba de ver.

    Es la única ground truth alcanzable en la demo: sin ella no existe Hit
    Rate@K, Recall@K, Precision@K, MRR ni NDCG@K, solo telemetría. Se guarda
    (session_id + id del evento + valor + canciones) en logs/feedback_*.jsonl
    para cruzarlo después con logs/events_*.jsonl.
    """
    data = request.get_json(silent=True) or {}
    if not limitador_feedback.permitir(request.remote_addr or "desconocida"):
        metrics.record_bloqueo()
        return jsonify({"error": "Demasiados avisos seguidos, espera un momento."}), 429
    # Topes de longitud: en la demo pública cualquier texto llega directo al log.
    session_id = (data.get("session_id") or "").strip()[:64]
    evento_id = (data.get("evento_id") or "").strip()[:80]
    valor = (data.get("valor") or "").strip().lower()
    if valor not in ("gust", "no_gust"):
        return jsonify({"error": "valor debe ser 'gust' o 'no_gust'"}), 400
    if not evento_id:
        return jsonify({"error": "falta evento_id del turno"}), 400
    sesion = CONVERSACIONES.get(session_id) or {}
    contexto = (sesion.get("etiquetables") or {}).get(evento_id) or {}
    cancion = (data.get("track_name") or "").strip()[:120]
    metrics.record_feedback({
        "session_id": session_id,
        "evento_id": evento_id,
        "valor": valor,
        "track_name": cancion,
        "turno": contexto.get("turno"),
        "query_en": contexto.get("query_en", ""),
        "cobertura_m3": contexto.get("cobertura_m3"),
    })
    return jsonify({"status": "ok", "evento_id": evento_id})


@app.route("/api/metrics")
def get_metrics():
    """El panel del frontend lo pinta en vivo; en la demo pública sale recortado.

    `errores` guarda los mensajes crudos de las últimas excepciones (pueden
    citar rutas del contenedor o fragmentos de una consulta). Con ADMIN_TOKEN
    correcto se devuelve el resumen completo, que es como lo leo desde la VM.
    """
    resumen = metrics.get_summary()
    token = os.getenv("ADMIN_TOKEN", "").strip()
    if not token or (request.headers.get("X-Admin-Token") or "").strip() != token:
        resumen["errores"] = []
    return jsonify(resumen)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    print(f"🚀 EchoPulse AI iniciando en http://localhost:{port}")
    print(f"💻 Device: {module2.device}")
    print(f"📊 Métricas habilitadas en {LOGS_DIR}")
    print(f"🔄 Flujo corregido: Módulo 2 (Retrieval) → Módulo 3 (Re-ranking)")
    print(f"🗣️ Cadena LLM: {' → '.join(llm.estado()['orden']) or '(vacía)'}")
    llm.precalentar()  # carga Qwen local en segundo plano (no bloquea el arranque)
    app.run(debug=debug, host="0.0.0.0", port=port)