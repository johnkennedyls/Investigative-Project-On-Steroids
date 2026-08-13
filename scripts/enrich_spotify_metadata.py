# scripts/enrich_spotify_metadata.py
"""
Enriquece module3_ids.json usando la Spotify Web API.
Requiere: pip install spotipy python-dotenv
"""
import json
import time
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Instalar spotipy si no está disponible
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
except ImportError:
    print("❌ Instalando spotipy...")
    os.system("pip install spotipy")
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials

# =====================================================================
# CONFIGURACIÓN
# =====================================================================
load_dotenv()  # Cargar variables de entorno desde .env

# Credenciales (prioriza .env, luego hardcoded para desarrollo)
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "TU_CLIENT_ID_AQUI")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "TU_CLIENT_SECRET_AQUI")

# Rutas
BASE_DIR = Path(__file__).parent.parent
INPUT_PATH = BASE_DIR / "echopulse_llm_orquestator" / "models" / "module3_ids.json"
OUTPUT_PATH = BASE_DIR / "echopulse_llm_orquestator" / "models" / "song_metadata.json"

# Configuración de rate limiting (Spotify permite ~100 requests/segundo)
BATCH_SIZE = 50  # Procesar en lotes para no saturar
DELAY_BETWEEN_BATCHES = 1  # Segundos entre lotes

# =====================================================================
# FUNCIÓN PRINCIPAL
# =====================================================================
def enrich_metadata():
    """Enriquece los IDs de Spotify con metadatos reales."""
    
    # Validar credenciales
    if CLIENT_ID == "TU_CLIENT_ID_AQUI" or CLIENT_SECRET == "TU_CLIENT_SECRET_AQUI":
        print("❌ ERROR: Configura tus credenciales de Spotify.")
        print("   Opción 1: Edita este script y reemplaza CLIENT_ID/CLIENT_SECRET")
        print("   Opción 2: Crea un archivo .env con SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET")
        print("   Obtén tus credenciales en: https://developer.spotify.com/dashboard")
        return False
    
    # Cargar IDs existentes
    print(f"🔍 Cargando IDs desde {INPUT_PATH}...")
    try:
        with open(INPUT_PATH, "r", encoding="utf-8") as f:
            metadata_cache = json.load(f)
        total_ids = len(metadata_cache)
        print(f"✅ Cargados: {total_ids:,} IDs")
    except FileNotFoundError:
        print(f"❌ No se encontró: {INPUT_PATH}")
        print("   Primero ejecuta: python extract_module3_ids.py")
        return False
    
    # Contar cuántos ya están enriquecidos
    already_enriched = sum(1 for m in metadata_cache.values() if m.get("track_name") and m["track_name"] != "Unknown")
    pending = total_ids - already_enriched
    print(f"📊 Estado: {already_enriched:,} ya enriquecidos | {pending:,} pendientes")
    
    if pending == 0:
        print("✅ ¡Todos los IDs ya tienen metadatos! No hay nada que hacer.")
        return True
    
    # Configurar cliente de Spotify
    print("\n🔐 Conectando a Spotify API...")
    try:
        auth_manager = SpotifyClientCredentials(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET
        )
        sp = spotipy.Spotify(client_credentials_manager=auth_manager)
        # Test de conexión
        sp.track("4iV5W9uYEdYUVa79Axb7Rh")  # "New Rules" de Dua Lipa (ID público)
        print("✅ Conexión exitosa a Spotify API")
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        print("   Verifica que tus credenciales sean correctas y estén activas.")
        return False
    
    # Filtrar IDs pendientes de enriquecer
    pending_ids = [
        sid for sid, meta in metadata_cache.items() 
        if not meta.get("track_name") or meta["track_name"] in [None, "Unknown", ""]
    ]
    
    print(f"\n🚀 Iniciando enriquecimiento de {len(pending_ids):,} IDs...")
    print(f"   Lotes de {BATCH_SIZE} | Delay: {DELAY_BETWEEN_BATCHES}s entre lotes\n")
    
    # Procesar en lotes
    enriched_count = 0
    error_count = 0
    
    for batch_start in range(0, len(pending_ids), BATCH_SIZE):
        batch = pending_ids[batch_start:batch_start + BATCH_SIZE]
        batch_num = (batch_start // BATCH_SIZE) + 1
        total_batches = (len(pending_ids) + BATCH_SIZE - 1) // BATCH_SIZE
        
        print(f"📦 Lote {batch_num}/{total_batches} (IDs {batch_start+1}-{min(batch_start+BATCH_SIZE, len(pending_ids))})")
        
        for i, song_id in enumerate(batch, 1):
            try:
                # Consultar track por ID
                track = sp.track(song_id, market=None)  # market=None para resultados globales
                
                # Extraer metadatos
                metadata_cache[song_id] = {
                    "track_name": track["name"],
                    "artist_name": track["artists"][0]["name"],
                    "album_name": track["album"]["name"],
                    "release_date": track["album"].get("release_date", "Unknown"),
                    "popularity": track.get("popularity", 0),
                    "genres": track["artists"][0].get("genres", [])[:3],  # Top 3 géneros del artista
                    "duration_ms": track.get("duration_ms"),
                    "explicit": track.get("explicit", False),
                    "source": "spotify_api",
                    "enriched_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                enriched_count += 1
                
                # Progreso en línea
                if i % 10 == 0 or i == len(batch):
                    progress = (batch_start + i) / len(pending_ids) * 100
                    print(f"   ✅ [{i}/{len(batch)}] {song_id[:12]}... → {track['name'][:40]}... ({progress:.1f}%)")
                    
            except spotipy.exceptions.SpotifyException as e:
                # ID no encontrado o eliminado
                if e.http_status == 404:
                    metadata_cache[song_id]["track_name"] = "Not Found on Spotify"
                    metadata_cache[song_id]["artist_name"] = "Unknown"
                    metadata_cache[song_id]["error"] = "404_not_found"
                    error_count += 1
                else:
                    print(f"   ⚠️ Error Spotify para {song_id[:12]}...: {e}")
                    error_count += 1
                    
            except Exception as e:
                print(f"   ❌ Error inesperado para {song_id[:12]}...: {type(e).__name__}: {e}")
                error_count += 1
                # Continuar con el siguiente en lugar de fallar todo el lote
        
        # Guardar progreso parcial cada lote (para no perder trabajo si se interrumpe)
        if batch_num % 5 == 0 or batch_num == total_batches:
            print(f"\n💾 Guardando progreso parcial...")
            with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                json.dump(metadata_cache, f, indent=2, ensure_ascii=False)
            print(f"   ✅ Guardado: {OUTPUT_PATH}")
        
        # Delay entre lotes para respetar rate limits
        if batch_start + BATCH_SIZE < len(pending_ids):
            time.sleep(DELAY_BETWEEN_BATCHES)
    
    # Guardar resultado final
    print(f"\n💾 Guardando resultado final...")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata_cache, f, indent=2, ensure_ascii=False)
    
    # Reporte final
    print(f"\n{'='*70}")
    print(f"📊 RESUMEN FINAL")
    print(f"{'='*70}")
    print(f"• IDs totales procesados: {len(pending_ids):,}")
    print(f"• ✅ Enriquecidos exitosamente: {enriched_count:,} ({100*enriched_count/len(pending_ids):.1f}%)")
    print(f"• ❌ Errores/No encontrados: {error_count:,} ({100*error_count/len(pending_ids):.1f}%)")
    print(f"• 📁 Archivo guardado: {OUTPUT_PATH}")
    print(f"• 📦 Tamaño estimado: {OUTPUT_PATH.stat().st_size / 1e6:.2f} MB")
    print(f"{'='*70}")
    
    # Mostrar ejemplos
    print(f"\n🎵 EJEMPLOS ENRIQUECIDOS:")
    examples = [
        (sid, meta) for sid, meta in metadata_cache.items() 
        if meta.get("track_name") and meta["track_name"] not in ["Unknown", "Not Found on Spotify"]
    ][:5]
    
    for sid, meta in examples:
        print(f"   • {meta['track_name']} — {meta['artist_name']} [{meta.get('genres', ['Unknown'])[0]}]")
    
    return True

# =====================================================================
# ENTRY POINT
# =====================================================================
if __name__ == "__main__":
    print("🎵 EchoPulse AI — Enriquecimiento de Metadatos con Spotify API")
    print(f"{'='*70}\n")
    
    success = enrich_metadata()
    
    if success:
        print(f"\n✅ Proceso completado. Ahora ejecuta: python app.py")
        sys.exit(0)
    else:
        print(f"\n❌ Proceso fallido. Revisa los errores arriba.")
        sys.exit(1)