"""
precompute_embeddings.py  —  EchoPulse AI
==========================================
Genera embeddings.pt con el vector 512-d de cada canción de la tabla maestra.

UBICACIÓN: colócalo dentro de  api_service/
EJECUCIÓN : python precompute_embeddings.py

Estructura del repositorio asumida:
  Investigative-Project-On-Steroids/
  ├── api_service/
  │   ├── app.py
  │   └── precompute_embeddings.py   ← ESTE SCRIPT
  ├── tabla_maestra/                 ← busca .parquet aquí y en sub-dirs
  ├── mst_mr_final.pth               ← checkpoint (raíz del repo)
  └── embeddings.pt                  ← se CREA aquí (raíz del repo)
"""

import argparse
import hashlib
import os
import re
import sys
import time

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.preprocessing import MinMaxScaler
import torch.serialization

torch.serialization.add_safe_globals([MinMaxScaler])

# ─────────────────────────────────────────────────────────────────────────────
# Rutas por defecto relativas a api_service/
# ─────────────────────────────────────────────────────────────────────────────
REPO_ROOT     = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DEFAULT_MODEL = os.path.join(REPO_ROOT, 'mst_mr_final.pth')
DEFAULT_OUT   = os.path.join(REPO_ROOT, 'embeddings.pt')

# Carpetas candidatas de datos en orden de preferencia
DATA_CANDIDATES = [
    os.path.join(REPO_ROOT, 'tabla_maestra', 'train'),
    os.path.join(REPO_ROOT, 'tabla_maestra'),
    os.path.join(REPO_ROOT, 'recommender_data_final_uni'),
    os.path.join(REPO_ROOT, 'master_dataset_73k'),
    os.path.join(REPO_ROOT, 'talkplay_datasets_divididos'),
    os.path.join(REPO_ROOT, 'wasabi_full_parquet_nofilters'),
]


# ─────────────────────────────────────────────────────────────────────────────
# Modelo  (idéntico al de app.py)
# ─────────────────────────────────────────────────────────────────────────────
class MST_MR_Transformer(nn.Module):
    def __init__(self, vocab_size, n_tech=26, d_model=512,
                 nhead=8, num_layers=6, max_len=151):
        super().__init__()
        self.lyric_emb       = nn.Embedding(vocab_size, d_model, padding_idx=0)
        self.pos_encoding    = nn.Parameter(torch.zeros(1, max_len, d_model))
        self.tech_projection = nn.Sequential(
            nn.Linear(n_tech, 256), nn.GELU(), nn.Linear(256, d_model)
        )
        self.cross_attn  = nn.MultiheadAttention(d_model, nhead, batch_first=True)
        self.norm_fusion = nn.LayerNorm(d_model)
        decoder_layer    = nn.TransformerDecoderLayer(
            d_model=d_model, nhead=nhead, batch_first=True
        )
        self.decoder = nn.TransformerDecoder(decoder_layer, num_layers=num_layers)
        self.fc_out  = nn.Linear(d_model, d_model)

    def forward(self, lyrics_idx, tech_features):
        x_lyric  = (self.lyric_emb(lyrics_idx)
                    + self.pos_encoding[:, :lyrics_idx.size(1), :])
        x_tech   = self.tech_projection(tech_features).unsqueeze(1)
        attn_out, _ = self.cross_attn(x_lyric, x_tech, x_tech)
        memory   = self.norm_fusion(attn_out + x_lyric)
        dec_out  = self.decoder(x_lyric, memory)
        return self.fc_out(torch.mean(dec_out, dim=1))   # (B, 512)


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────────────────────────────────────
def find_parquets(base_dir: str) -> list:
    """Busca recursivamente archivos .parquet dentro de base_dir."""
    found = []
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.endswith('.parquet'):
                found.append(os.path.join(root, f))
    return sorted(found)


def auto_detect_data_dir() -> str:
    """Devuelve la primera carpeta candidata que contenga al menos un .parquet."""
    for candidate in DATA_CANDIDATES:
        if os.path.isdir(candidate) and find_parquets(candidate):
            return candidate
    raise FileNotFoundError(
        "No se encontraron .parquet en ninguna carpeta candidata.\n"
        "Carpetas buscadas:\n" +
        "\n".join("  " + c for c in DATA_CANDIDATES) +
        "\n\nUsa --data <ruta> para especificar la carpeta manualmente."
    )


def load_dataframe(data_dir: str) -> pd.DataFrame:
    """Carga y concatena todos los .parquet del directorio."""
    files = find_parquets(data_dir)
    if not files:
        raise FileNotFoundError(f"No hay .parquet en: {data_dir}")

    print(f"  Archivos encontrados ({len(files)}):")
    dfs = []
    for f in files:
        rel     = os.path.relpath(f, REPO_ROOT)
        size_mb = os.path.getsize(f) / 1e6
        print(f"    {rel}  ({size_mb:.1f} MB)")
        dfs.append(pd.read_parquet(f))

    df = pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]
    print(f"  OK: {len(df):,} filas x {len(df.columns)} columnas")
    return df


def detect_lyric_col(cols: list) -> str:
    """Detecta la columna de letras por nombre."""
    priorities = [
        'lyrics_cleaned', 'lyrics_clean', 'lyrics', 'lyric',
        'letra', 'text', 'words', 'song_text', 'content',
    ]
    # Coincidencia exacta primero
    for name in priorities:
        if name in cols:
            return name
    # Coincidencia parcial
    for name in priorities:
        for c in cols:
            if name in c.lower():
                return c
    return None


def detect_tech_cols(cols: list, n: int = 26) -> list:
    """
    Detecta hasta `n` columnas de features técnicos por nombre.
    Si no hay suficientes, completa con columnas numéricas al final.
    """
    keywords = {
        'bpm', 'energy', 'danc', 'loud', 'valen', 'acou', 'instr',
        'live', 'speech', 'tempo', 'key', 'mode', 'time_sig',
        'duration', 'popular', 'explicit', 'target', 'beat',
        'chorus', 'section', 'year', 'month', 'disc', 'track_num',
    }
    matched = [c for c in cols if any(k in c.lower() for k in keywords)]

    if len(matched) >= n:
        return matched[:n]

    # Rellenar con columnas no incluidas aún
    remaining = [c for c in cols if c not in matched]
    return (matched + remaining)[:n]


def clean_text(text: str) -> list:
    return re.sub(r'[^a-zA-Z\s]', '', str(text).lower()).split()


def words_to_tokens(words: list, vocab: dict, max_len: int = 151) -> list:
    """Tokeniza con fallback de prefijos para OOV (FIX 4)."""
    tokens = []
    for w in words[:max_len]:
        if w in vocab:
            tokens.append(vocab[w])
        else:
            matched = False
            for pl in (5, 4, 3):
                if len(w) > pl and w[:pl] in vocab:
                    tokens.append(vocab[w[:pl]])
                    matched = True
                    break
            if not matched:
                tokens.append(1)   # <UNK>
    tokens += [0] * (max_len - len(tokens))
    return tokens


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Pre-cómputo
# ─────────────────────────────────────────────────────────────────────────────
def precompute(df, model, vocab, scaler, lyric_col, tech_cols,
               batch_size=64, device='cpu'):
    model.eval()
    model.to(device)
    all_embs = []
    n  = len(df)
    t0 = time.time()

    for start in range(0, n, batch_size):
        batch = df.iloc[start: start + batch_size]

        # Tokenizar letras
        token_batch = [
            words_to_tokens(clean_text(str(row[lyric_col])), vocab)
            for _, row in batch.iterrows()
        ]

        # Features técnicos → numerico → escalar
        tech_vals = (
            batch[tech_cols]
            .apply(pd.to_numeric, errors='coerce')
            .fillna(0.5)
            .values
            .astype(float)
        )

        # Garantizar exactamente 26 columnas para el scaler
        if tech_vals.shape[1] > 26:
            tech_vals = tech_vals[:, :26]
        elif tech_vals.shape[1] < 26:
            pad       = np.full((tech_vals.shape[0], 26 - tech_vals.shape[1]), 0.5)
            tech_vals = np.hstack([tech_vals, pad])

        try:
            tech_scaled = scaler.transform(tech_vals)
        except Exception:
            tech_scaled = tech_vals   # fallback sin escalar

        l_t = torch.tensor(token_batch, dtype=torch.long).to(device)
        t_t = torch.tensor(tech_scaled, dtype=torch.float).to(device)

        with torch.no_grad():
            emb = model(l_t, t_t).cpu()
        all_embs.append(emb)

        done    = min(start + batch_size, n)
        pct     = 100 * done / n
        elapsed = time.time() - t0
        eta     = (elapsed / done) * (n - done) if done else 0
        print(f"\r  [{done:>6,}/{n:,}]  {pct:5.1f}%  ETA: {eta:5.0f}s",
              end='', flush=True)

    print()
    return torch.cat(all_embs, dim=0)   # (n_songs, 512)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Pre-computa embeddings de canciones para EchoPulse AI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python precompute_embeddings.py
  python precompute_embeddings.py --data ../tabla_maestra
  python precompute_embeddings.py --device cuda --batch 128
        """,
    )
    parser.add_argument('--model',  default=DEFAULT_MODEL)
    parser.add_argument('--data',   default=None,
                        help='Directorio con .parquet (default: auto-detectado)')
    parser.add_argument('--out',    default=DEFAULT_OUT)
    parser.add_argument('--batch',  type=int, default=64)
    parser.add_argument('--device', default='cpu')
    args = parser.parse_args()

    print("=" * 62)
    print("  EchoPulse AI — Pre-computo de embeddings")
    print("=" * 62)

    # ── 1. Verificar checkpoint ──────────────────────────────────
    rel_model = os.path.relpath(args.model, REPO_ROOT)
    print(f"\n[1/5] Checkpoint : {rel_model}")
    if not os.path.exists(args.model):
        print(f"  ERROR: No encontrado: {args.model}", file=sys.stderr)
        sys.exit(1)
    print(f"  OK  ({os.path.getsize(args.model)/1e6:.1f} MB)")

    # ── 2. Cargar modelo ─────────────────────────────────────────
    print("\n[2/5] Cargando modelo...")
    checkpoint = torch.load(args.model, map_location='cpu', weights_only=False)

    # Soportar dos convenciones de clave posibles
    state_key = 'model' if 'model' in checkpoint else 'model_state_dict'
    vocab     = checkpoint['vocab']
    scaler    = checkpoint['scaler']

    model = MST_MR_Transformer(vocab_size=len(vocab))
    model.load_state_dict(checkpoint[state_key])
    model.eval()
    print(f"  OK  vocabulario: {len(vocab):,} palabras")

    # ── 3. Localizar datos ───────────────────────────────────────
    print("\n[3/5] Localizando datos...")
    data_dir = args.data or auto_detect_data_dir()
    print(f"  Dir : {os.path.relpath(data_dir, REPO_ROOT)}")
    df = load_dataframe(data_dir)

    # ── 4. Detectar columnas ─────────────────────────────────────
    print("\n[4/5] Detectando columnas...")
    cols      = df.columns.tolist()
    lyric_col = detect_lyric_col(cols)
    tech_cols = detect_tech_cols(cols, n=26)

    if lyric_col is None:
        print("  ERROR: No se encontró columna de letras.", file=sys.stderr)
        print(f"  Columnas disponibles: {cols}", file=sys.stderr)
        sys.exit(1)

    print(f"  Letras    : '{lyric_col}'")
    sample_tech = ', '.join(tech_cols[:5]) + ('...' if len(tech_cols) > 5 else '')
    print(f"  Tecnicos  : {len(tech_cols)} cols  ({sample_tech})")

    # ── 5. Pre-computar ──────────────────────────────────────────
    print(f"\n[5/5] Generando embeddings  "
          f"(n={len(df):,}, batch={args.batch}, device={args.device})...")
    t0  = time.time()
    emb = precompute(df, model, vocab, scaler, lyric_col, tech_cols,
                     batch_size=args.batch, device=args.device)
    elapsed = time.time() - t0
    print(f"  OK  shape: {emb.shape}  —  {elapsed:.1f}s")

    # ── Guardar ──────────────────────────────────────────────────
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    torch.save(emb, args.out)
    out_mb = os.path.getsize(args.out) / 1e6
    print(f"\n  Guardado: {os.path.relpath(args.out, REPO_ROOT)}  ({out_mb:.1f} MB)")

    # ── SHA-256 del checkpoint para FIX 6 ───────────────────────
    pth_hash = sha256_file(args.model)
    print(f"\n{'=' * 62}")
    print("  SHA-256 del checkpoint — pega esto en app.py (FIX 6):")
    print(f"{'=' * 62}")
    print(f"\n  verify_checkpoint(MODEL_PATH, expected_sha256=")
    print(f"      '{pth_hash}')")
    print(f"\n{'=' * 62}")
    print("  Listo. Ejecuta:  python app.py")
    print(f"{'=' * 62}\n")


if __name__ == '__main__':
    main()
