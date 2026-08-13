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
cd api_service
python app.py
```

Then open your browser at `http://localhost:5000` (or whichever port is configured).

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
