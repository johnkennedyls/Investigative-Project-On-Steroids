# scripts/cross_kaggle_metadata.py
"""
Cruza los Spotify IDs del Módulo 3 con spotify_data.csv de Kaggle
para enriquecer song_metadata.json con nombres reales de canciones.
"""
import pandas as pd
import json
import pickle
from pathlib import Path
import time
import sys

# =====================================================================
# CONFIGURACIÓN DE RUTAS (AJUSTA SEGÚN TU ESTRUCTURA)
# =====================================================================
BASE_DIR = Path(__file__).parent.parent

# 📁 CSV de Kaggle (nombre exacto que mencionaste)
KAGGLE_CSV = BASE_DIR / "spotify_data.csv"

# 📁 IDs del Módulo 3 desde song_map.pkl
MODULE3_IDS_PATH = BASE_DIR / "echopulse_llm_orquestator" / "models" / "talkplay" / "song_map.pkl"

# 📁 Salida: Cache enriquecido para app.py
OUTPUT_PATH = BASE_DIR / "echopulse_llm_orquestator" / "models" / "song_metadata.json"

# =====================================================================
# FUNCIONES AUXILIARES
# =====================================================================
def load_module3_ids(path: Path) -> set:
    """Carga los Spotify IDs del Módulo 3 desde song_map.pkl."""
    with open(path, "rb") as f:
        song2idx = pickle.load(f)
    return set(song2idx.keys())

def detect_columns(df: pd.DataFrame) -> dict:
    """Detecta automáticamente las columnas relevantes por nombres comunes."""
    cols_lower = {c.lower().strip(): c for c in df.columns}
    mapping = {}
    
    # 🔍 Buscar columna de ID de Spotify (priorizar track_id)
    id_patterns = ["track_id", "spotify_id", "id", "spotify_track_id", "trackid"]
    for pattern in id_patterns:
        if pattern in cols_lower:
            mapping["id"] = cols_lower[pattern]
            print(f"   📍 ID de Spotify → '{cols_lower[pattern]}'")
            break
    
    # 🎵 Buscar nombre de canción
    name_patterns = ["track_name", "name", "title", "song_name", "trackname", "song"]
    for pattern in name_patterns:
        if pattern in cols_lower:
            mapping["track_name"] = cols_lower[pattern]
            print(f"   📍 Nombre de canción → '{cols_lower[pattern]}'")
            break
    
    # 🎤 Buscar artista
    artist_patterns = ["artist_name", "artist", "artists", "performer", "artistname"]
    for pattern in artist_patterns:
        if pattern in cols_lower:
            mapping["artist_name"] = cols_lower[pattern]
            print(f"   📍 Artista → '{cols_lower[pattern]}'")
            break
    
    # 🎼 Buscar género
    genre_patterns = ["genre", "genres", "category", "musical_genre", "genre_lyr"]
    for pattern in genre_patterns:
        if pattern in cols_lower:
            mapping["genre"] = cols_lower[pattern]
            print(f"   📍 Género → '{cols_lower[pattern]}'")
            break
    
    # 💿 Buscar álbum (opcional)
    album_patterns = ["album_name", "album", "album_title", "albumname"]
    for pattern in album_patterns:
        if pattern in cols_lower:
            mapping["album_name"] = cols_lower[pattern]
            print(f"   📍 Álbum → '{cols_lower[pattern]}'")
            break
    
    return mapping

# =====================================================================
# PROCESO PRINCIPAL
# =====================================================================
def cross_reference():
    print("🚀 EchoPulse AI — Cruce con spotify_data.csv de Kaggle")
    print("=" * 70)
    
    # 1. Verificar que el CSV existe
    if not KAGGLE_CSV.exists():
        print(f"❌ ERROR: No se encontró {KAGGLE_CSV}")
        print(f"   Asegúrate de que el archivo esté en: {BASE_DIR}")
        return False
    
    # 2. Cargar IDs del Módulo 3
    print(f"\n[1/4] Cargando IDs del Módulo 3...")
    module3_ids = load_module3_ids(MODULE3_IDS_PATH)
    print(f"   ✅ {len(module3_ids):,} Spotify IDs cargados desde song_map.pkl")
    
    # 3. Cargar CSV de Kaggle
    print(f"\n[2/4] Cargando {KAGGLE_CSV.name}...")
    try:
        start = time.time()
        df = pd.read_csv(KAGGLE_CSV, dtype={"track_id": str, "id": str})  # Forzar string para IDs
        load_time = time.time() - start
        print(f"   ✅ {len(df):,} filas × {len(df.columns)} columnas en {load_time:.1f}s")
    except Exception as e:
        print(f"❌ Error cargando CSV: {e}")
        return False
    
    # 4. Detectar columnas clave
    print(f"\n[3/4] Detectando columnas...")
    col_map = detect_columns(df)
    
    if "id" not in col_map:
        print("❌ ERROR: No se encontró columna con ID de Spotify")
        print(f"   Columnas disponibles: {list(df.columns)[:15]}")
        return False
    
    # 5. Cruce y enriquecimiento
    print(f"\n[4/4] Cruzando {len(module3_ids):,} IDs con {len(df):,} filas...")
    
    id_col = col_map["id"]
    
    # Filtrar solo filas que coinciden con nuestros IDs del Módulo 3
    df_filtered = df[df[id_col].isin(module3_ids)].copy()
    matched_count = len(df_filtered)
    
    print(f"   🔍 Coincidencias encontradas: {matched_count:,} ({100*matched_count/len(module3_ids):.1f}%)")
    
    # Construir diccionario de metadatos
    metadata_cache = {}
    
    for _, row in df_filtered.iterrows():
        song_id = str(row[id_col]).strip()
        
        metadata_cache[song_id] = {
            "track_name": str(row.get(col_map.get("track_name"), "Unknown")).strip() or "Unknown",
            "artist_name": str(row.get(col_map.get("artist_name"), "Unknown")).strip() or "Unknown",
            "genre": str(row.get(col_map.get("genre"), "Unknown")).strip() if col_map.get("genre") else "Unknown",
            "album_name": str(row.get(col_map.get("album_name"), "Unknown")).strip() if col_map.get("album_name") else "Unknown",
            "source": "kaggle_spotify_data_csv",
            "popularity": row.get("popularity"),
            "duration_ms": row.get("duration_ms"),
            "explicit": bool(row.get("explicit", False)) if "explicit" in df.columns else None
        }
    
    # Añadir IDs no encontrados con fallback (para que el frontend los maneje)
    matched_ids = set(metadata_cache.keys())
    missing_ids = module3_ids - matched_ids
    
    for song_id in missing_ids:
        metadata_cache[song_id] = {
            "track_name": "Unknown",
            "artist_name": "Unknown",
            "genre": "Unknown",
            "source": "not_found_in_kaggle_csv"
        }
    
    # Guardar resultado
    print(f"\n💾 Guardando cache enriquecido...")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata_cache, f, indent=2, ensure_ascii=False)
    
    # Reporte final
    enriched = matched_count
    missing = len(missing_ids)
    
    print(f"\n{'='*70}")
    print(f"📊 RESUMEN DEL CRUCE")
    print(f"{'='*70}")
    print(f"• IDs totales del Módulo 3: {len(module3_ids):,}")
    print(f"• Filas en spotify_data.csv: {len(df):,}")
    print(f"• ✅ Coincidencias enriquecidas: {enriched:,} ({100*enriched/len(module3_ids):.1f}%)")
    print(f"• ❌ Sin coincidencia (fallback): {missing:,}")
    print(f"• 📁 Archivo guardado: {OUTPUT_PATH}")
    print(f"• 📦 Tamaño estimado: {OUTPUT_PATH.stat().st_size / 1e6:.2f} MB")
    print(f"{'='*70}")
    
    # Mostrar ejemplos
    print(f"\n🎵 EJEMPLOS ENRIQUECIDOS:")
    examples = [(sid, meta) for sid, meta in metadata_cache.items() 
                if meta["source"] == "kaggle_spotify_data_csv"][:5]
    
    for sid, meta in examples:
        print(f"   • {meta['track_name']} — {meta['artist_name']} [{meta['genre']}]")
    
    if missing > 0:
        print(f"\n⚠️ {missing:,} IDs no encontrados en el CSV.")
        print(f"   El frontend mostrará el ID con enlace funcional de Spotify.")
    
    return True

# =====================================================================
# ENTRY POINT
# =====================================================================
if __name__ == "__main__":
    success = cross_reference()
    
    if success:
        print(f"\n✅ ¡Listo! Ahora:")
        print(f"   1. Reinicia tu servidor: python app.py")
        print(f"   2. Tu frontend mostrará nombres reales de canciones 🎵")
        print(f"   3. Los enlaces de Spotify/YouTube funcionarán para todos los IDs")
        sys.exit(0)
    else:
        print(f"\n❌ Error en el proceso. Revisa los mensajes arriba.")
        sys.exit(1)