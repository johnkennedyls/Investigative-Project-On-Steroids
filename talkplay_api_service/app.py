import os
import re
import json
import pickle
import torch
import torch.nn as nn
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# --- 1. CONFIGURACIÓN Y CARGA DE MODELO ---
MODEL_PATH = "intent_model.pth"
VOCAB_PATH = "vocab.json"
SONG_MAP_PATH = "song_map.pkl"

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
try:
    with open(VOCAB_PATH, "r") as f:
        vocab = json.load(f)
    with open(SONG_MAP_PATH, "rb") as f:
        song2idx = pickle.load(f)
        idx2song = {i: s for s, i in song2idx.items()}

    model = IntentTransformer(len(vocab), len(song2idx))
    model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
    model.eval()
    print("✅ Módulo 3 cargado correctamente.")
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
            
            # Por ahora devolvemos el ID y un nombre ficticio para el prototipo
            results.append({
                "track_name": f"Track ID: {song_id[:8]}...",
                "artist_name": "Recomendación EchoPulse",
                "similarity": similarity
            })

        return jsonify(results)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)