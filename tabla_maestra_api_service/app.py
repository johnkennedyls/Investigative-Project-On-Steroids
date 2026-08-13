from flask import Flask, render_template, request, jsonify
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import pandas as pd
import os
import re
import math
import unicodedata
from sklearn.preprocessing import MinMaxScaler
import torch.serialization

# Permitir carga del escalador
torch.serialization.add_safe_globals([MinMaxScaler])

app = Flask(__name__)

# --- CONFIGURACIÓN DE RUTAS ---
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_PATH = os.path.join(BASE_DIR, 'tabla_maestra/train')
MODEL_PATH = os.path.join(BASE_DIR, 'mst_mr_final.pth')
EMBEDDINGS_PATH = os.path.join(BASE_DIR, 'embeddings.pt')

# --- ARQUITECTURA ORIGINAL ---
class MST_MR_Transformer(nn.Module):
    def __init__(self, vocab_size, n_tech=26, d_model=512, nhead=8, num_layers=6, max_len=151):
        super().__init__()
        self.lyric_emb = nn.Embedding(vocab_size, d_model)
        self.pos_encoding = nn.Parameter(torch.zeros(1, max_len, d_model))
        self.tech_projection = nn.Sequential(nn.Linear(n_tech, 256), nn.GELU(), nn.Linear(256, d_model))
        self.cross_attn = nn.MultiheadAttention(d_model, nhead, batch_first=True)
        self.norm_fusion = nn.LayerNorm(d_model)
        decoder_layer = nn.TransformerDecoderLayer(d_model=d_model, nhead=nhead, batch_first=True)
        self.decoder = nn.TransformerDecoder(decoder_layer, num_layers=num_layers)
        self.fc_out = nn.Linear(d_model, d_model)

    def forward(self, lyrics_idx, tech_features):
        x_lyric = self.lyric_emb(lyrics_idx) + self.pos_encoding[:, :lyrics_idx.size(1), :]
        x_tech = self.tech_projection(tech_features).unsqueeze(1)
        attn_out, _ = self.cross_attn(x_lyric, x_tech, x_tech)
        memory = self.norm_fusion(attn_out + x_lyric)
        dec_out = self.decoder(x_lyric, memory)
        return self.fc_out(torch.mean(dec_out, dim=1))

# --- CARGA DE ACTIVOS ---
print("--- 🧠 Cargando Cerebro MST-MR y Datos ---")
checkpoint = torch.load(MODEL_PATH, map_location='cpu', weights_only=False)
vocab = checkpoint['vocab']
scaler = checkpoint['scaler']
model = MST_MR_Transformer(vocab_size=len(vocab))
model.load_state_dict(checkpoint['model'])
model.eval()

files = [f for f in os.listdir(DATA_PATH) if f.endswith('.parquet')]
df_ref = pd.read_parquet(os.path.join(DATA_PATH, files[0]))

# Detectar columnas (usando las que viste en consola: track_title, artist_name)
t_col = next((c for c in df_ref.columns if 'track' in c.lower() or 'title' in c.lower()), 'track_title')
a_col = next((c for c in df_ref.columns if 'artist' in c.lower()), 'artist_name')

# Embeddings y Jaccard
song_embeddings = None
if os.path.exists(EMBEDDINGS_PATH):
    song_embeddings = torch.load(EMBEDDINGS_PATH, map_location='cpu')
    if isinstance(song_embeddings, dict): song_embeddings = song_embeddings.get('embeddings')

l_col = 'lyrics_cleaned' if 'lyrics_cleaned' in df_ref.columns else 'lyrics'
lyric_word_sets = [set(str(l).split()) for l in df_ref[l_col]]

print(f"--- ✅ Sistema Listo | Columnas: {t_col}, {a_col} ---")

def clean_text_advanced(text):
    if not text: return ""
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode('utf-8')
    text = re.sub(r'[^a-z0-9\s]', '', text.lower())
    return text.strip()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/predict', methods=['POST'])
def predict():
    try:
        data = request.json
        raw_lyrics = data.get('lyrics', '')
        cleaned_str = clean_text_advanced(raw_lyrics)
        words = cleaned_str.split()

        if len(words) < 2:
            return jsonify({"error": "Escribe una frase más larga"}), 400

        # 1. Inferencia Neural
        tokens = [vocab.get(w, 1) for w in words][:151]
        tokens += [0] * (151 - len(tokens))
        t_neutral = np.zeros((1, 26)) 
        
        with torch.no_grad():
            query_emb = F.normalize(model(torch.tensor([tokens]), torch.tensor(t_neutral).float()), dim=1)
            if song_embeddings is not None:
                neural_sim = F.cosine_similarity(query_emb, song_embeddings, dim=1)
            else:
                neural_sim = torch.zeros(len(df_ref))

        # 2. Jaccard
        query_set = set(words)
        jaccard = torch.tensor([
            len(query_set & ws) / len(query_set | ws) if (query_set | ws) else 0.0
            for ws in lyric_word_sets
        ], dtype=torch.float)

        # 3. Score y Limpieza de NaNs (IMPORTANTE)
        neural_sim = torch.nan_to_num(neural_sim, nan=0.0)
        jaccard = torch.nan_to_num(jaccard, nan=0.0)
        
        ALPHA, GAMMA = 0.40, 0.60
        score = (ALPHA * neural_sim) + (GAMMA * jaccard)

        # 4. Top 10
        k = min(10, len(score))
        top_val, top_idx = torch.topk(score, k=k)

        res = []
        for val, idx in zip(top_val.tolist(), top_idx.tolist()):
            row = df_ref.iloc[idx]
            
            # Validación final de NaN para JSON
            safe_sim = float(val)
            if math.isnan(safe_sim) or math.isinf(safe_sim):
                safe_sim = 0.0

            res.append({
                "track_name": str(row[t_col]),
                "artist_name": str(row[a_col]),
                "similarity": safe_sim
            })
            
        return jsonify(res)

    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)