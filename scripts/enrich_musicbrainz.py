# scripts/enrich_musicbrainz.py
"""
Enriquece module3_ids.json usando MusicBrainz API (gratis, sin auth).
Requiere: pip install requests
"""
import json
import time
import requests
from pathlib import Path

# Configuración
BASE_DIR = Path(__file__).parent.parent
INPUT_PATH = BASE_DIR / "echopulse_llm_orquestator" / "models" / "module3_ids.json"
OUTPUT_PATH = BASE_DIR / "echopulse_llm_orquestator" / "models" / "song_metadata.json"

# User-Agent requerido por MusicBrainz
HEADERS = {
    "User-Agent": "EchoPulseAI/1.0 (tu_email@ejemplo.com)",
    "Accept": "application/json"
}

def fetch_from_musicbrainz(spotify_id):
    """Busca metadata en MusicBrainz usando el Spotify ID como external link."""
    try:
        # Buscar recording por enlace externo de Spotify
        url = f"https://musicbrainz.org/ws/2/recording/"
        params = {
            "query": f"url:https://open.spotify.com/track/{spotify_id}",
            "fmt": "json",
            "limit": 1
        }
        response = requests.get(url, params=params, headers=HEADERS, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("recordings"):
                rec = data["recordings"][0]
                
                # Extraer artista
                artist_name = "Unknown"
                if rec.get("artist-credit"):
                    artist_name = rec["artist-credit"][0].get("name", "Unknown")
                
                # Extrair géneros (vía tags)
                genres = [tag["name"] for tag in rec.get("tags", [])[:3]] if rec.get("tags") else []
                
                return {
                    "track_name": rec.get("title", "Unknown"),
                    "artist_name": artist_name,
                    "album_name": rec.get("release", "Unknown"),
                    "genres": genres,
                    "duration_ms": rec.get("length"),
                    "source": "musicbrainz_api",
                    "musicbrainz_id": rec.get("id")
                }
        
        # Fallback: buscar por ID en texto libre (menos preciso)
        url2 = f"https://musicbrainz.org/ws/2/recording/"
        params2 = {
            "query": f'"{spotify_id}"',
            "fmt": "json", 
            "limit": 1
        }
        response2 = requests.get(url2, params=params2, headers=HEADERS, timeout=10)
        if response2.status_code == 200:
            data2 = response2.json()
            if data2.get("recordings"):
                rec = data2["recordings"][0]
                return {
                    "track_name": rec.get("title", "Unknown"),
                    "artist_name": rec.get("artist-credit", [{}])[0].get("name", "Unknown"),
                    "source": "musicbrainz_fallback"
                }
                
    except Exception as e:
        print(f"   ⚠️ Error MusicBrainz para {spotify_id[:12]}...: {e}")
    
    return None

def enrich_with_musicbrainz():
    # Cargar IDs
    print(f"🔍 Cargando {INPUT_PATH}...")
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        metadata_cache = json.load(f)
    
    pending = [sid for sid, meta in metadata_cache.items() 
               if not meta.get("track_name") or meta["track_name"] in [None, "Unknown"]]
    
    print(f"🚀 Enriqueciendo {len(pending):,} IDs con MusicBrainz...")
    
    enriched = 0
    for i, spotify_id in enumerate(pending):
        result = fetch_from_musicbrainz(spotify_id)
        
        if result:
            metadata_cache[spotify_id].update(result)
            enriched += 1
            if i % 50 == 0:
                print(f"   ✅ [{i+1}/{len(pending)}] {spotify_id[:12]}... → {result.get('track_name', 'Unknown')[:40]}")
        else:
            metadata_cache[spotify_id]["track_name"] = "Not Found"
            metadata_cache[spotify_id]["artist_name"] = "Unknown"
        
        # Rate limit: 1 request/segundo recomendado
        time.sleep(1.0)
    
    # Guardar resultado
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata_cache, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Listo: {enriched}/{len(pending)} IDs enriquecidos con MusicBrainz")
    print(f"📁 Guardado en: {OUTPUT_PATH}")

if __name__ == "__main__":
    enrich_with_musicbrainz()