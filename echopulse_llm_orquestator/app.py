# app.py - EchoPulse AI Orchestrator (FLUJO CORREGIDO)
# Módulos: Módulo 2 (Retrieval) → Módulo 3 (Re-ranking)

import json
import requests
import time
import os
import re
import math
import pickle
import hashlib
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

# =====================================================================
# CONFIGURACIÓN DE LOGGING Y MÉTRICAS
# =====================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/metrics.log', encoding='utf-8', mode='a'),
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
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)
HF_TOKEN = os.getenv("HF_TOKEN")
if not HF_TOKEN or not HF_TOKEN.startswith("hf_"):
    raise ValueError("❌ Configura HF_TOKEN en tu archivo .env")

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# =====================================================================
# 📊 SISTEMA DE MÉTRICAS SIMPLE
# =====================================================================
class SimpleMetrics:
    def __init__(self):
        self.counters = defaultdict(int)
        self.timings = defaultdict(list)
        self._lock = Lock()
        self.metrics_file = LOGS_DIR / f"metrics_{datetime.now().strftime('%Y-%m')}.jsonl"
    
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
    
    def record_query(self, success=True, error=None, metadata_hits=0, metadata_misses=0):
        with self._lock:
            self.counters["total_queries"] += 1
            if success:
                self.counters["successful_queries"] += 1
            else:
                self.counters["failed_queries"] += 1
            self.counters["metadata_hits"] += metadata_hits
            self.counters["metadata_misses"] += metadata_misses
            record = {
                "timestamp": datetime.now().isoformat(),
                "success": success, "error": error,
                "metadata_hits": metadata_hits, "metadata_misses": metadata_misses,
                "avg_latency_ms": np.mean(self.timings.get("total", [0])) if self.timings.get("total") else 0
            }
            with open(self.metrics_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    def get_summary(self):
        with self._lock:
            total = self.counters["total_queries"]
            return {
                "total_queries": total,
                "success_rate": (self.counters["successful_queries"] / total * 100) if total > 0 else 0,
                "metadata_coverage": (self.counters["metadata_hits"] / (self.counters["metadata_hits"] + self.counters["metadata_misses"]) * 100) if (self.counters["metadata_hits"] + self.counters["metadata_misses"]) > 0 else 0,
                "avg_latency_ms": np.mean(self.timings.get("total", [0])) if self.timings.get("total") else 0
            }

metrics = SimpleMetrics()

# =====================================================================
# 🎯 UTILIDADES: Cache de Metadatos + Enlaces Reales
# =====================================================================
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

def generar_enlaces_reales(song_id: str, metadata: dict = None) -> dict:
    if metadata is None: metadata = obtener_metadata(song_id)
    track = metadata.get("track_name", "Unknown")
    artist = metadata.get("artist_name", "Unknown")
    genre = metadata.get("genre", "Unknown")
    
    is_spotify_id = bool(song_id and len(song_id) == 22 and song_id.isalnum() and not song_id.startswith("TR"))
    
    if is_spotify_id:
        spotify_url = f"https://open.spotify.com/track/{song_id}"
    else:
        query = f"{artist} {track}".strip()
        spotify_url = f"https://open.spotify.com/search/{urllib.parse.quote(query)}" if query else "https://open.spotify.com"
    
    if track != "Unknown" and artist != "Unknown":
        yt_query = f"{artist} {track} official audio"
    elif genre != "Unknown":
        yt_query = f"{genre} music official"
    else:
        yt_query = "music"
    
    youtube_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(yt_query.strip())}"
    
    return {"spotify_url": spotify_url, "youtube_url": youtube_url, "youtube_query": yt_query.strip()}

def enriquecer_candidato(candidato: dict) -> dict:
    song_id = candidato.get("id", "")
    metadata = obtener_metadata(song_id)
    enlaces = generar_enlaces_reales(song_id, metadata)
    return {**candidato, **metadata, **enlaces}

# =====================================================================
# 🌐 HUGGING FACE - Qwen 2.5
# =====================================================================
MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
API_URL = "https://router.huggingface.co/v1/chat/completions"
HF_HEADERS = {"Authorization": f"Bearer {HF_TOKEN}", "Content-Type": "application/json"}

def query_hugging_face(user_prompt, system_prompt="", max_tokens=256, temperature=0.2):
    payload = {
        "model": MODEL_ID,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": max_tokens, "temperature": temperature, "top_p": 0.9, "stream": False
    }
    for attempt in range(3):
        try:
            response = requests.post(API_URL, headers=HF_HEADERS, json=payload, timeout=60)
            if response.status_code == 503:
                wait = int(response.headers.get("Retry-After", 2 ** attempt))
                print(f"⏳ Cold start: esperando {wait}s...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            result = response.json()
            if "choices" in result and result["choices"]:
                return result["choices"][0]["message"]["content"].strip()
        except requests.exceptions.Timeout:
            print(f"⏳ Timeout (intento {attempt+1}/3)")
        except Exception as e:
            print(f"❌ Error HF (intento {attempt+1}): {e}")
        if attempt < 2:
            time.sleep(2 ** attempt)
    return user_prompt

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
            
            self.lyric_word_sets = [set(str(l).split()) for l in self.df_ref[self.l_col].fillna("")]
            print(f"✅ Módulo 2 listo | Canciones: {len(self.df_ref)} | Vocab: {len(self.vocab)}")
        else:
            print("⚠️ Módulo 2: Sin datos de referencia. Usando fallback.")
    
    def tokenize(self, text, max_len=151):
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", str(text).lower())
        tokens = [self.vocab.get(w, self.vocab.get("<UNK>", 1)) for w in cleaned.split()][:max_len]
        tokens += [0] * (max_len - len(tokens))
        return torch.tensor([tokens], device=self.device)
    
    def retrieve_top10(self, user_query_en, k=10):
        """🔍 RETRIEVAL PRINCIPAL: Busca en Tabla Maestra por similitud lírica+técnica."""
        if self.df_ref is None or len(self.df_ref) == 0:
            # Fallback: retornar IDs dummy si no hay datos
            return [{"id": f"fallback_{i}", "similarity": 0.5 - i*0.05, "track_name": "Unknown", "artist_name": "Unknown"} for i in range(k)]
        
        tokens = self.tokenize(user_query_en)
        tech_neutral = torch.zeros(1, 26, device=self.device)
        query_set = set(re.sub(r"[^a-zA-Z0-9\s]", "", user_query_en.lower()).split())
        
        with torch.no_grad():
            query_emb = F.normalize(self.model(tokens, tech_neutral), dim=1)
            neural_sim = F.cosine_similarity(query_emb, self.song_embeddings.to(self.device), dim=1)
            
            jaccard_scores = []
            for ws in self.lyric_word_sets:
                union = query_set | ws
                jaccard_scores.append(len(query_set & ws) / len(union) if union else 0.0)
            jaccard_scores = torch.tensor(jaccard_scores, device=self.device)
            
            # Score ponderado: 40% neural + 60% léxico
            neural_sim = torch.nan_to_num(neural_sim, nan=0.0)
            jaccard_scores = torch.nan_to_num(jaccard_scores, nan=0.0)
            score = 0.40 * neural_sim + 0.60 * jaccard_scores
            
            k = min(k, len(score))
            top_val, top_idx = torch.topk(score, k)
        
        results = []
        for val, idx in zip(top_val.tolist(), top_idx.tolist()):
            row = self.df_ref.iloc[idx]
            safe_sim = float(val)
            if math.isnan(safe_sim) or math.isinf(safe_sim): safe_sim = 0.0
            results.append({
                "id": str(row.get("id", row.get("msd_id", f"unknown_{idx}"))),
                "track_name": str(row.get(self.t_col, "Unknown")),
                "artist_name": str(row.get(self.a_col, "Unknown")),
                "genre": str(row.get("genre_lyr", row.get("genre", "Unknown"))),
                "similarity": round(safe_sim, 4),
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
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._load()
    def _load(self):
        print(f"🔌 Cargando Módulo 3 (IntentTransformer - Re-ranking) en {self.device}...")
        with open(self.path / "vocab.json", "r", encoding="utf-8") as f: self.vocab = json.load(f)
        with open(self.path / "song_map.pkl", "rb") as f:
            song2idx = pickle.load(f)
            self.idx2song = {i: s for s, i in song2idx.items()}
        self.model = IntentTransformer(len(self.vocab), len(song2idx), max_len=512).to(self.device)
        self.model.load_state_dict(torch.load(self.path / "intent_model.pth", map_location=self.device, weights_only=True))
        self.model.eval()
        print(f"✅ Módulo 3 listo | Clases: {len(song2idx)} | Vocab: {len(self.vocab)}")
    
    def tokenize(self, text, max_len=512):
        cleaned = re.sub(r"[^a-zA-Z0-9\s?]", "", str(text).lower())
        tokens = [self.vocab.get(t, self.vocab.get("<UNK>", 1)) for t in cleaned.split()][:max_len]
        tokens += [0] * (max_len - len(tokens))
        return torch.tensor([tokens], device=self.device)
    
    def rerank_candidates(self, candidates: list, user_query_en: str) -> list:
        """🎯 RE-RANKING: Ajusta el orden del Top 10 según intención conversacional."""
        if not candidates: return candidates
        tokens = self.tokenize(user_query_en)
        with torch.no_grad():
            logits = self.model(tokens)
            probs = F.softmax(logits, dim=1)[0]
        
        # Calcular score de intención para cada candidato
        scored = []
        for c in candidates:
            song_id = c.get("id", "")
            if song_id in self.idx2song.values():
                idx = list(self.idx2song.keys())[list(self.idx2song.values()).index(song_id)]
                intent_score = probs[idx].item() if idx < len(probs) else 0.0
            else:
                # Fallback: score basado en similitud de texto (heurístico)
                intent_score = 0.5  # Neutral si no está en vocabulario del módulo 3
            scored.append({**c, "intent_score": round(intent_score, 4)})
        
        # Re-ordenar: 70% score original (Módulo 2) + 30% intención (Módulo 3)
        for s in scored:
            s["final_score"] = 0.70 * s.get("similarity", 0) + 0.30 * s.get("intent_score", 0)
        
        scored.sort(key=lambda x: x["final_score"], reverse=True)
        for i, item in enumerate(scored): item["rank"] = i + 1
        return scored[:10]

# =====================================================================
# 🚀 INICIALIZACIÓN DE MÓDULOS (ORDEN CORREGIDO)
# =====================================================================
cargar_metadata_cache(MODELS_DIR)
module2 = Module2MasterTable(MODELS_DIR)  # 🔍 Retrieval Principal
module3 = Module3IntentReranker(MODELS_DIR)  # 🎯 Re-ranking Semántico

# =====================================================================
# 🎵 ORQUESTADOR PRINCIPAL (FLUJO CORREGIDO)
# =====================================================================
def procesar_consulta_echopulse(mensaje_usuario):
    query_start = time.time()
    stage_latencies = {}
    metadata_hits = metadata_misses = 0
    
    try:
        print(f"\n👤 Usuario: {mensaje_usuario}")
        
        # FASE 1: Traducción/refinamiento a inglés
        print("🔍 Fase 1: Refinando intención con Qwen 2.5...")
        t1 = time.time()
        system_translate = "You are a music curator assistant. Convert the user's request into 3-5 concise English keywords representing emotional state and musical preference. Output ONLY keywords, comma-separated."
        query_en = query_hugging_face(mensaje_usuario, system_translate, max_tokens=100)
        stage_latencies["translation"] = (time.time() - t1) * 1000
        print(f"   🎯 Keywords (EN): {query_en}")
        
        # FASE 2: 🔍 Módulo 2 - RETRIEVAL PRINCIPAL (Tabla Maestra)
        print("⚖️ Fase 2: Módulo 2 - Retrieval desde Tabla Maestra...")
        t2 = time.time()
        candidates_m2 = module2.retrieve_top10(query_en, k=10)
        stage_latencies["retrieval"] = (time.time() - t2) * 1000
        print(f"   📦 Retrieval: {len(candidates_m2)} candidatos iniciales")
        
        # FASE 3: 🎯 Módulo 3 - RE-RANKING SEMÁNTICO (Intención)
        print("🧠 Fase 3: Módulo 3 - Re-ranking por intención conversacional...")
        t3 = time.time()
        candidates_m3 = module3.rerank_candidates(candidates_m2, query_en)
        stage_latencies["reranking"] = (time.time() - t3) * 1000
        
        # Enriquecer con metadatos y enlaces
        candidates_final = [enriquecer_candidato(c) for c in candidates_m3]
        for c in candidates_final:
            if c.get("track_name") != "Unknown": metadata_hits += 1
            else: metadata_misses += 1
        print(f"   🔗 Enlaces generados | Meta: {metadata_hits}/{len(candidates_final)}")
        
        # FASE 4: Generar respuesta final con Qwen
        print("💬 Fase 4: Generando respuesta empática con Qwen 2.5...")
        t4 = time.time()
        contexto = "\n".join([f"{i+1}. [{c['id'][:12]}...] '{c.get('track_name', 'Unknown')}' por {c.get('artist_name', 'Unknown')}" for i, c in enumerate(candidates_final[:5])])
        system_final = "Eres EchoPulse AI, un curador musical empático y experto. Responde SIEMPRE en ESPAÑOL con tono cálido y natural. Usa la lista de canciones proporcionada para recomendar música. Sé conciso: 3-4 oraciones máximo."
        user_final = f"Candidatos recomendados:\n{contexto}\n\nConsulta original: {mensaje_usuario}"
        respuesta_final = query_hugging_face(user_final, system_final, max_tokens=350, temperature=0.4)
        stage_latencies["generation"] = (time.time() - t4) * 1000
        
        stage_latencies["total"] = (time.time() - query_start) * 1000
        metrics.record_query(success=True, metadata_hits=metadata_hits, metadata_misses=metadata_misses)
        
        print(f"\n📦 DEBUG - Módulo 2 Top 1 (Retrieval): {candidates_m2[0].get('track_name', 'Unknown')}")
        print(f"📦 DEBUG - Módulo 3 Top 1 (Re-ranked): {candidates_final[0].get('track_name', 'Unknown')}")
        print(f"📊 Métricas: {stage_latencies['total']:.0f}ms total | {metadata_hits}/{len(candidates_final)} con metadata")
        
        return {
            "response": respuesta_final, "query_en": query_en,
            "module2_retrieval": candidates_m2,  # 🔍 Resultados originales de retrieval
            "module3_reranked": candidates_final,  # 🎯 Resultados finales re-ordenados
            "stages": ["translation", "retrieval_m2", "reranking_m3", "generation"],
            "latencies_ms": {k: round(v, 1) for k, v in stage_latencies.items()}
        }
    except Exception as e:
        total_time = (time.time() - query_start) * 1000
        metrics.record_query(success=False, error=str(e))
        logger.error(f"❌ Error en consulta: {e}")
        raise

# =====================================================================
# 🌐 FLASK APP
# =====================================================================
app = Flask(__name__)

@app.route("/")
def home(): return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def api_chat():
    try:
        data = request.json
        mensaje = data.get("message", "").strip()
        if not mensaje: return jsonify({"error": "Mensaje vacío"}), 400
        resultado = procesar_consulta_echopulse(mensaje)
        return jsonify(resultado)
    except Exception as e:
        print(f"❌ Error en /api/chat: {e}")
        return jsonify({"error": str(e), "response": "Lo siento, tuve un problema técnico."}), 500

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "modules": {"hf_api": "connected", "module2_retrieval": "loaded", "module3_reranker": "loaded"}, "device": str(module2.device), "metrics": metrics.get_summary()})

@app.route("/api/metrics")
def get_metrics(): return jsonify(metrics.get_summary())

if __name__ == "__main__":
    print(f"🚀 EchoPulse AI iniciando en http://localhost:5000")
    print(f"💻 Device: {module2.device}")
    print(f"📊 Métricas habilitadas en {LOGS_DIR}")
    print(f"🔄 Flujo corregido: Módulo 2 (Retrieval) → Módulo 3 (Re-ranking)")
    app.run(debug=True, host="0.0.0.0", port=5000)