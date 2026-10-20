import os
import re
import sys
import json
import pickle
import torch
import torch.nn as nn
from flask import Flask, request, jsonify, render_template

sys.stdout.reconfigure(errors="replace")
sys.stderr.reconfigure(errors="replace")

app = Flask(__name__)

# --- 1. CONFIGURACIÓN Y CARGA DE MODELO ---
MODEL_PATH = "intent_model.pth"
VOCAB_PATH = "vocab.json"
SONG_MAP_PATH = "song_map.pkl"
METADATA_PATH = "song_metadata.json"

# Definir la arquitectura idéntica a la fase de entrenamiento
class IntentTransformer(nn.Module):
    def __init__(self, vocab_size, num_songs, d_model=256, n_heads=8):
        super().__init__()
        self.embed = nn.Embedding(vocab_size, d_model)
        self.pos = nn.Parameter(torch.randn(1, 512, d_model))
        self.encoder = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(d_model, n_heads, dim_feedforward=1024, batch_first=True),
            num_layers=4
        )
        self.fc = nn.Linear(d_model, num_songs)

    def forward(self, x):
        x = self.embed(x) + self.pos[:, :x.size(1), :]
        x = self.encoder(x)
        return self.fc(x.mean(dim=1))

# Cargar componentes globales
device = torch.device("cpu") # Usamos CPU para el servidor web
SONG_METADATA = {}
try:
    with open(VOCAB_PATH, "r") as f:
        vocab = json.load(f)
    with open(SONG_MAP_PATH, "rb") as f:
        song2idx = pickle.load(f)
        idx2song = {i: s for s, i in song2idx.items()}

    if os.path.exists(METADATA_PATH):
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            SONG_METADATA = json.load(f)

    model = IntentTransformer(len(vocab), len(song2idx))
    model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
    model.eval()
    print(f"✅ Módulo 3 cargado correctamente. Metadatos: {len(SONG_METADATA):,} canciones.")
except Exception as e:
    print(f"❌ Error cargando el modelo: {e}")

# --- 2. FUNCIONES DE APOYO ---
def tokenize(text, max_len=128):
    tokens = re.sub(r"[^a-zA-Z0-9\s?]", "", str(text).lower()).split()
    enc = [vocab.get(t, vocab["<UNK>"]) for t in tokens][:max_len]
    enc += [0] * (max_len - len(enc))
    return torch.tensor(enc).unsqueeze(0)

# --- 3. RUTAS DE LA API ---
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/predict", methods=["POST"])
def predict():
    try:
        data = request.json
        user_input = data.get("lyrics", "")
        
        if not user_input:
            return jsonify({"error": "No se recibió texto"}), 400

        # Inferencia
        tokens = tokenize(user_input)
        with torch.no_grad():
            outputs = model(tokens)
            probs = torch.softmax(outputs, dim=1)
            values, indices = torch.topk(probs, 10) # Pedimos Top 10

        results = []
        for i in range(10):
            song_id = idx2song[indices[0][i].item()]
            similarity = values[0][i].item()
            metadata = SONG_METADATA.get(song_id, {})
            track_name = metadata.get("track_name")
            artist_name = metadata.get("artist_name")

            results.append({
                "track_name": track_name if track_name not in [None, "Unknown", "Not Found", ""] else f"Canción {song_id[:8]}",
                "artist_name": artist_name if artist_name not in [None, "Unknown", "Not Found", ""] else "Artista desconocido",
                "similarity": similarity,
                "spotify_url": f"https://open.spotify.com/track/{song_id}"
            })

        return jsonify(results)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)