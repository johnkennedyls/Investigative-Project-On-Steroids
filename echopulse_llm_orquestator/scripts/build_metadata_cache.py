# scripts/build_metadata_cache.py
"""
Extrae todos los Spotify IDs de song_map.pkl y crea un cache de metadatos
usando tu parquet de Tabla Maestra.
"""
import json
import pickle
import pandas as pd
from pathlib import Path
import sys

# =====================================================================
# CONFIGURACIÓN DE RUTAS (AJUSTA SEGÚN TU ESTRUCTURA)
# =====================================================================
# Ruta base del proyecto
PROJECT_ROOT = Path(r"D:\FUP\2026-1\pi\Investigative-Project-On-Steroids")

# Paths de entrada
SONG_MAP_PATH = PROJECT_ROOT / "echopulse_llm_orquestator" / "models" / "talkplay" / "song_map.pkl"
PARQUET_PATH = PROJECT_ROOT / "tabla_maestra" / "train" / "part-00000-0cbbc0cd-4603-4851-afb0-2f9a0fa6eb89-c000.snappy.parquet"

# Path de salida
OUTPUT_PATH = PROJECT_ROOT / "echopulse_llm_orquestator" / "models" / "song_metadata.json"

# =====================================================================
# FUNCIÓN PRINCIPAL
# =====================================================================
def build_metadata_cache():
    print("🔍 Paso 1: Cargando song_map.pkl del Módulo 3...")
    
    # 1. Cargar song_map.pkl (ID de Spotify → índice del modelo)
    try:
        with open(SONG_MAP_PATH, "rb") as f:
            song2idx = pickle.load(f)
        spotify_ids = list(song2idx.keys())
        print(f"   ✅ {len(spotify_ids):,} IDs extraídos de song_map.pkl")
    except FileNotFoundError:
        print(f"❌ No se encontró: {SONG_MAP_PATH}")
        return
    except Exception as e:
        print(f"❌ Error cargando song_map.pkl: {e}")
        return
    
    # 2. Cargar parquet de Tabla Maestra
    print(f"\n📦 Paso 2: Cargando parquet: {PARQUET_PATH.name}")
    try:
        df = pd.read_parquet(PARQUET_PATH)
        print(f"   ✅ {len(df):,} filas cargadas | {len(df.columns)} columnas")
    except Exception as e:
        print(f"❌ Error cargando parquet: {e}")
        return
    
    # 3. Detectar columnas clave con fallback inteligente
    print("\n🔎 Paso 3: Detectando columnas...")
    
    def detect_column(df, patterns, default):
        """Busca columna por patrones de nombre (case-insensitive)."""
        cols_lower = {c.lower(): c for c in df.columns}
        for pattern in patterns:
            for col_lower, col_real in cols_lower.items():
                if pattern.lower() in col_lower:
                    print(f"   📍 '{pattern}' → '{col_real}'")
                    return col_real
        print(f"   ⚠️ '{patterns[0]}' no encontrado, usando fallback: '{default}'")
        return default
    
    # Detectar columnas
    id_col = detect_column(df, ["id", "spotify_id", "track_id", "spotify_track_id"], "id")
    track_col = detect_column(df, ["track_name", "track_title", "name", "title", "song"], "track_name")
    artist_col = detect_column(df, ["artist_name", "artist", "performer", "artist_names"], "artist_name")
    genre_col = detect_column(df, ["genre", "category", "musical_genre"], "genre")
    
    # 4. Crear índice por ID para búsqueda rápida
    print(f"\n🔗 Paso 4: Construyendo cache de metadatos...")
    if id_col not in df.columns:
        print(f"❌ Columna de ID '{id_col}' no encontrada en el parquet")
        print(f"   Columnas disponibles: {list(df.columns)[:10]}...")
        return
    
    df_indexed = df.set_index(id_col)
    
    metadata_cache = {}
    matched = 0
    
    for song_id in spotify_ids:
        if song_id in df_indexed.index:
            row = df_indexed.loc[song_id]
            metadata_cache[song_id] = {
                "track_name": str(row.get(track_col, "Unknown")).strip() or "Unknown",
                "artist_name": str(row.get(artist_col, "Unknown")).strip() or "Unknown",
                "genre": str(row.get(genre_col, "Unknown")).strip() or "Unknown" if genre_col in df.columns else "Unknown"
            }
            matched += 1
        else:
            # Fallback para IDs no encontrados en parquet
            metadata_cache[song_id] = {
                "track_name": "Unknown",
                "artist_name": "Unknown", 
                "genre": "Unknown"
            }
    
    # 5. Guardar resultado
    print(f"\n💾 Paso 5: Guardando cache en {OUTPUT_PATH}")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata_cache, f, indent=2, ensure_ascii=False)
    
    # 6. Reporte final
    print(f"\n{'='*60}")
    print(f"📊 RESUMEN DEL PROCESO")
    print(f"{'='*60}")
    print(f"• IDs totales de song_map.pkl: {len(spotify_ids):,}")
    print(f"• Filas en parquet: {len(df):,}")
    print(f"• ✅ Coincidencias encontradas: {matched:,} ({100*matched/len(spotify_ids):.1f}%)")
    print(f"• ❌ Fallback 'Unknown': {len(spotify_ids) - matched:,}")
    print(f"• 📁 Cache guardado: {OUTPUT_PATH}")
    print(f"{'='*60}")
    
    # 7. Mostrar ejemplos
    print(f"\n🎵 EJEMPLOS DEL CACHE:")
    examples = [(sid, meta) for sid, meta in metadata_cache.items() if meta["track_name"] != "Unknown"][:5]
    for i, (sid, meta) in enumerate(examples, 1):
        print(f"   {i}. {sid[:12]}... → '{meta['track_name']}' por {meta['artist_name']} [{meta['genre']}]")
    
    if not examples:
        print("   ⚠️ No se encontraron coincidencias. Verifica que los IDs en song_map.pkl coincidan con la columna '{id_col}' del parquet.")

if __name__ == "__main__":
    build_metadata_cache()