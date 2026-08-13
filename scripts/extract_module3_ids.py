# extract_module3_ids.py
"""
Extrae todos los Spotify IDs del song_map.pkl del Módulo 3 (IntentTransformer)
y crea un archivo JSON base para metadatos.
"""
import pickle
import json
from pathlib import Path

# =====================================================================
# CONFIGURACIÓN DE RUTAS
# =====================================================================
BASE_DIR = Path(__file__).parent
SONG_MAP_PATH = BASE_DIR / "echopulse_llm_orquestator" / "models" / "talkplay" / "song_map.pkl"
OUTPUT_PATH = BASE_DIR / "echopulse_llm_orquestator" / "models" / "module3_ids.json"

# =====================================================================
# EXTRACCIÓN
# =====================================================================
def extract_spotify_ids():
    print("🔍 Cargando song_map.pkl del Módulo 3...")
    
    try:
        with open(SONG_MAP_PATH, "rb") as f:
            song2idx = pickle.load(f)
        
        print(f"✅ Cargado: {len(song2idx):,} entradas")
        
        # Extraer solo los IDs de Spotify (las claves del diccionario)
        spotify_ids = list(song2idx.keys())
        
        print(f"📦 IDs de Spotify extraídos: {len(spotify_ids):,}")
        
        # Crear estructura base de metadatos (skeleton)
        # Los campos track_name/artist_name se llenarán después
        metadata_skeleton = {}
        for song_id in spotify_ids:
            metadata_skeleton[song_id] = {
                "track_name": None,      # Se llenará después
                "artist_name": None,     # Se llenará después
                "genre": None,           # Se llenará después
                "source": "module3_intent_transformer"
            }
        
        # Guardar resultado
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(metadata_skeleton, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Guardado en: {OUTPUT_PATH}")
        print(f"📊 Resumen:")
        print(f"   • Total IDs: {len(spotify_ids):,}")
        print(f"   • Formato: JSON con campos null listos para enriquecer")
        
        # Mostrar ejemplos
        print(f"\n🎵 Ejemplos de IDs extraídos:")
        for i, sid in enumerate(spotify_ids[:5], 1):
            print(f"   {i}. {sid}")
        
        return spotify_ids
        
    except FileNotFoundError:
        print(f"❌ Error: No se encontró {SONG_MAP_PATH}")
        print(f"   Verifica que el archivo song_map.pkl existe en la ruta correcta.")
        return None
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return None

if __name__ == "__main__":
    extract_spotify_ids()