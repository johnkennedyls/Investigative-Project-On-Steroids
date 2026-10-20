# scripts/build_fame_index.py
"""
Construye el índice de fama (popularidad Spotify) a partir de tracks.csv.

Salida: echopulse_llm_orquestator/models/fame_index.parquet
  - filas tipo='artista'  → (artista_norm, '', max popularity del artista)
  - filas tipo='cancion'  → (artista_norm, titulo_norm, popularity del track)

Uso: python scripts/build_fame_index.py
"""
import ast
import re
import sys
import time

import pandas as pd
from pathlib import Path

# Windows: consolas cp1252 no pueden imprimir emojis → no romper
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except AttributeError:
    pass

BASE_DIR = Path(__file__).parent.parent
TRACKS_CSV = BASE_DIR / "tracks.csv"
OUT_PATH = BASE_DIR / "echopulse_llm_orquestator" / "models" / "fame_index.parquet"


def _norm(s) -> str:
    s = re.sub(r"[^a-z0-9 ]", "", str(s).lower())
    return re.sub(r"\s+", " ", s).strip()


def _parse_artists(x):
    if isinstance(x, str) and x.startswith("["):
        try:
            vals = list(ast.literal_eval(x))
            return [v for v in vals if v and str(v).strip()]
        except Exception:
            return [x]
    return [str(x)]


def build_fame_index():
    print("🔥 EchoPulse AI — Índice de fama desde tracks.csv")
    print("=" * 70)

    if not TRACKS_CSV.exists():
        print(f"❌ No se encontró {TRACKS_CSV}")
        return False

    print("\n[1/4] Cargando tracks.csv (solo columnas necesarias)...")
    t0 = time.time()
    df = pd.read_csv(TRACKS_CSV, usecols=["name", "artists", "popularity"], low_memory=False)
    df["popularity"] = pd.to_numeric(df["popularity"], errors="coerce")
    df = df[df["popularity"].notna()]
    print(f"   ✅ {len(df):,} tracks con popularity válida | {time.time()-t0:.1f}s")

    print("\n[2/4] Normalizando claves (artista, título)...")
    df["artista_n"] = df["artists"].apply(lambda x: _norm(_parse_artists(x)[0] if _parse_artists(x) else ""))
    df["titulo_n"] = df["name"].apply(_norm)
    df = df[df["artista_n"] != ""]

    print("\n[3/4] Agregando: popularity máxima por artista y por (artista, título)...")
    art = (df.groupby("artista_n", as_index=False)["popularity"].max()
             .rename(columns={"popularity": "pop"}))
    art.insert(0, "tipo", "artista")
    art.insert(2, "titulo_n", "")
    art.insert(3, "pop", art.pop("pop"))
    art.columns = ["tipo", "artista_n", "titulo_n", "pop"]

    can = (df.groupby(["artista_n", "titulo_n"], as_index=False)["popularity"].max()
             .rename(columns={"popularity": "pop"}))
    can.insert(0, "tipo", "cancion")

    idx = pd.concat([art, can], ignore_index=True)[["tipo", "artista_n", "titulo_n", "pop"]]
    idx["pop"] = idx["pop"].astype("int16")

    print(f"   🎤 artistas únicos: {len(art):,} | 🎵 claves (artista,título): {len(can):,}")

    print("\n[4/4] Guardando índice...")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    idx.to_parquet(OUT_PATH, index=False)
    print(f"   📁 {OUT_PATH} ({OUT_PATH.stat().st_size / 1e6:.1f} MB)")

    print("\n" + "=" * 70)
    print("✅ Listo. Reinicia el servidor EchoPulse para usar la señal de fama.")
    return True


if __name__ == "__main__":
    ok = build_fame_index()
    raise SystemExit(0 if ok else 1)
