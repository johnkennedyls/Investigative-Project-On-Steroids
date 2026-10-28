# 🎵 Music Recommender System — Investigative Project On Steroids

> A content-based and semantic music recommendation system built on ~73,000 songs, trained on rich metadata and lyrics spanning 1950–2019.

---

## 🧩 Problem Statement

Music streaming platforms rely heavily on collaborative filtering — if you and another user share listening habits, you get the same recommendations. This approach fails for niche tastes, new users (cold-start problem), and ignores the **actual content** of music: its lyrics, themes, mood, and cultural context.

This project builds a **content-aware music recommender** that understands songs by what they *are*, not just who else listened to them. Using the [WASABI](https://wasabi.i3s.unice.fr/) dataset enriched with lyrics from 1950 to 2019, the system learns semantic representations of songs and recommends music based on musical and lyrical similarity.

---

## 🏗️ Architecture & Pipeline

```
Raw Sources
  ├── WASABI Dataset (full parquet, no filters)
  └── Lyrics 1950–2019

        │
        ▼
   ETL & Preprocessing
   (Cleaning, merging, feature engineering)
        │
        ▼
   Tabla Maestra (~73k songs)
   (Unified master dataset with metadata + lyrics)
        │
        ▼
   Transformer-based Embedding Model
   (mst_mr_final.pth — trained with PyTorch)
        │
        ▼
   Recommender Engine
   (Cosine similarity over learned embeddings)
        │
        ▼
   API Service (FastAPI / Flask)
   └── HTML Frontend
```

### Key Components

| Component | Description |
|---|---|
| `wasabi_full_parquet_nofilters/` | Raw WASABI dataset in Parquet format |
| `lirycs1950-2019/` | Lyrics corpus spanning 70 years |
| `tabla_maestra/` | ETL output: master table with unified features |
| `master_dataset_73k/` | Final cleaned dataset (~73,000 songs) |
| `recommender_data_final_uni/` | Pre-computed embeddings and recommender index |
| `talkplay_datasets_divididos/` | Partitioned datasets for training and evaluation |
| `docs/` | Notebooks documenting the transformer pipeline |
| `mst_mr_final.pth` | Trained PyTorch model weights |
| `api_service/` | REST API + HTML frontend for serving recommendations |

---

## 📊 Results & Metrics

The model was evaluated using standard information retrieval metrics on a held-out split of the master dataset:

| Metric | Score |
|---|---|
| Precision@10 | — |
| Recall@10 | — |
| NDCG@10 | — |
| Coverage | — |

> ⚠️ Metrics table to be filled in after final evaluation run. See `docs/Tabla_Maestra_Transformer.ipynb` for the evaluation pipeline.

**Qualitative results:** The system successfully surfaces thematically and sonically similar songs across genres and decades, including cross-era recommendations (e.g., a 1970s folk song recommended alongside a 2000s indie track with similar lyrical themes).

---

## 🚀 Getting Started

### Prerequisites

- Python 3.9+
- Git LFS (the datasets are stored with Git Large File Storage)

```bash
git lfs install
git clone https://github.com/johnkennedyls/Investigative-Project-On-Steroids.git
cd Investigative-Project-On-Steroids
```

### Install dependencies

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Run the API

```bash
cd echopulse_llm_orquestator
pip install -r requirements.txt
python app.py
```

Then open your browser at `http://localhost:5000` (or whichever port is configured).

### Voice (LLM) — free Qwen

The agent answers with Qwen through `echopulse_llm_orquestator/llm_client.py`,
which tries several providers in order and skips the ones that fail. Hugging
Face's router no longer serves Qwen for free (HTTP 402: no credits), so the
default working path is a local Qwen via Ollama:

```bash
ollama pull hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M   # or qwen2.5:1.5b-instruct-q4_K_M on CPU
python app.py
```

Other free options (a Hugging Face Space of your own, Groq, Alibaba DashScope)
are configured in `.env` — see [`.env.example`](echopulse_llm_orquestator/.env.example)
and the technical write-up [`docs/LLM_QWEN_GRATIS.md`](docs/LLM_QWEN_GRATIS.md).

### Deploy to Hugging Face Spaces

Step-by-step guide (in Spanish, written for a first deployment):
[`docs/DESPLIEGUE_HF.md`](docs/DESPLIEGUE_HF.md). It covers the three pieces
(artifacts repo + app Space + Qwen Space), the exact commands, verification and
the usual build/runtime failures.

```powershell
python deploy\subir_artefactos.py --dry-run                 # 216 MB de pesos
powershell -File deploy\preparar_space_app.ps1              # carpeta lista para el Space
```

### Public demo (Azure VM, 24/7)

`deploy/azure-compose.yaml` runs the whole agent on one Ubuntu VM: the Flask
orchestrator plus Qwen 2.5-1.5B served by llama.cpp (CPU, no GPU cost) on the
free Azure for Students credit. Link to share (nothing in front of the app):
**https://zero-programming-opens-detroit.trycloudflare.com/**

```bash
sudo docker compose up -d --build app     # only the app service, never `down`
sudo docker compose --profile cf up -d tunnel-cf          # Cloudflare tunnel (no token needed)
sudo docker compose --profile tunnel up -d tunnel         # ngrok backup (NGROK_AUTHTOKEN in .env)
sudo docker compose exec -T app python scripts/evaluar_metricas.py
```

Two tunnels for two different needs. Cloudflare Quick Tunnels are free, need no
account and show no interstitial, but the `*.trycloudflare.com` hostname is assigned
when the tunnel starts: after a restart the link changes, so re-read it with
`sudo docker logs echopulse-tunnel-cf-1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com'`
and re-share it. ngrok keeps a permanent hostname
(**https://myself-private-trilogy.ngrok-free.dev/**) as the fallback; its free tier
puts a one-time warning page in front of browser traffic, which a browser cannot skip
with a header (the cookie hides it for 7 days), and `index.html` sends
`ngrok-skip-browser-warning` on every `fetch` so the JSON calls never receive HTML.
Quotas to watch: ngrok 20,000 requests and 1 GB out per month; Quick Tunnels have no
uptime guarantee and answer 429 above 200 in-flight requests, which the 12 turns/min
per IP cap keeps far away.

Both tunnels terminate TLS outside the VM, so the VM only makes outbound connections
and inbound port 80 stays closed at the NSG
(`az network nsg rule update -g rg-echopulse-demo --nsg-name echopulse-demo-nsg -n permitir-web-80 --access Deny`;
`--access Allow` restores plain HTTP on `64.236.242.123`).

Guardrails in the app: 12 turns/min per IP on `/api/chat`, 40/min on `/api/feedback`,
16 KB body cap, and `/api/llm/*` disabled unless `ADMIN_TOKEN` is set. Behind the
tunnel the visitor IP arrives in `X-Forwarded-For`, and `limite.ip_cliente` only
trusts that header when the connection comes from the tunnel (otherwise the whole
public would share one bucket, and anyone could forge the header to escape the limit).
Every turn is appended to `logs/events_*.jsonl` and every 👍/👎 to
`logs/feedback_*.jsonl` (Docker volume `app-logs`); `scripts/evaluar_metricas.py`
crosses them into the Hit Rate / Recall / Precision / MRR / NDCG report used by the
thesis.

Useful checks:

```bash
python scripts/test_llm.py                      # offline tests (402/429, conversation engine)
curl -X POST http://localhost:5000/api/llm/probar
python scripts/simular_conversacion.py --turnos 5   # simulated 5-turn conversation
```


### Explore the notebooks

Open `docs/Tabla_Maestra_Transformer.ipynb` to walk through the full pipeline: ETL, embedding generation, and recommendation logic.

---

## 🛠️ Tech Stack

- **Python** — pandas, numpy, PyTorch, scikit-learn
- **Apache Parquet** — efficient columnar storage for large datasets
- **PyTorch** — transformer model for song embeddings
- **FastAPI / Flask** — REST API for serving recommendations
- **Git LFS** — version control for large binary files (~1.1 GB of datasets)

---

## 📁 Repository Structure

```
Investigative-Project-On-Steroids/
├── api_service/                  # API backend + HTML frontend
├── docs/                         # Jupyter notebooks & analysis
├── lirycs1950-2019/              # Raw lyrics corpus
├── master_dataset_73k/           # Final processed dataset
├── recommender_data_final_uni/   # Recommender embeddings & index
├── tabla_maestra/                # Intermediate ETL output
├── talkplay_datasets_divididos/  # Train/val/test splits
├── wasabi_full_parquet_nofilters/# Raw WASABI data
├── mst_mr_final.pth              # Trained model weights
└── README.md
```

---

## 👤 Author

**John Kennedy Landazuri Sandoval**
— Universidad FUP · 2026-1 · Proyecto Investigativo

---

## 📄 License

No license specified yet. Recommended: [MIT License](https://choosealicense.com/licenses/mit/).
