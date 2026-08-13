# scripts/cross_tracks_csv.py
"""
Cruza los IDs restantes (desconocidos) con tracks.csv para enriquecer 
song_metadata.json con nombre y artista.
"""
import pandas as pd
import json
from pathlib import Path
import time

# =====================================================================
# CONFIGURACIÓN DE RUTAS
# =====================================================================
BASE_DIR = Path(__file__).parent.parent

# Entrada: Metadata actual (con ~20k Unknown)
METADATA_PATH = BASE_DIR / "echopulse_llm_orquestator" / "models" / "song_metadata.json"

# Entrada: Nuevo CSV con IDs de Spotify
TRACKS_CSV = BASE_DIR / "tracks.csv"  # Ajusta si está en otra carpeta

# Salida: Se sobreescribe METADATA_PATH con los nuevos datos

# =====================================================================
# PROCESO PRINCIPAL
# =====================================================================
def enrich_from_tracks_csv():
    print("🚀 EchoPulse AI — Enriquecimiento con tracks.csv")
    print("=" * 70)
    
    # 1. Verificar archivos
    if not METADATA_PATH.exists():
        print(f"❌ No se encontró {METADATA_PATH}")
        return False
    if not TRACKS_CSV.exists():
        print(f"❌ No se encontró {TRACKS_CSV}")
        return False

    # 2. Cargar metadata actual
    print(f"\n[1/4] Cargando song_metadata.json...")
    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    
    # Filtrar solo IDs que aún son "Unknown"
    pending_ids = {
        song_id for song_id, meta in metadata.items()
        if meta.get("track_name") in [None, "Unknown", "Not Found", ""]
    }
    print(f"   🔍 IDs pendientes: {len(pending_ids):,}")
    if not pending_ids:
        print("   ✅ ¡Todos los IDs ya tienen nombre! No hay nada que hacer.")
        return True

    # 3. Cargar tracks.csv
    print(f"\n[2/4] Cargando {TRACKS_CSV.name}...")
    df = pd.read_csv(TRACKS_CSV, dtype={"id": str})  # Forzar string para evitar problemas numéricos
    print(f"   ✅ {len(df):,} filas × {len(df.columns)} columnas")

    # Normalizar IDs (quitar espacios, garantizar string)
    df["id"] = df["id"].astype(str).str.strip()

    # 4. Cruce
    print(f"\n[3/4] Cruzando IDs pendientes...")
    matches = df[df["id"].isin(pending_ids)].copy()
    matched_count = len(matches)
    print(f"   🔗 Coincidencias nuevas: {matched_count:,}")

    # Actualizar metadata
    newly_enriched = 0
    for _, row in matches.iterrows():
        song_id = row["id"]
        # Solo actualizar si aún es Unknown (evita sobreescribir datos previos)
        if metadata[song_id].get("track_name") in [None, "Unknown", "Not Found", ""]:
            metadata[song_id] = {
                "track_name": str(row["name"]).strip() or "Unknown",
                "artist_name": str(row["artists"]).strip() or "Unknown",
                "genre": "Unknown",  # Este CSV no tiene columna de género
                "source": "tracks_csv_enrichment",
                "popularity": row.get("popularity"),
                "duration_ms": row.get("duration_ms"),
                "explicit": bool(row.get("explicit", False)),
                "release_date": str(row.get("release_date", "Unknown")),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            newly_enriched += 1

    # 5. Guardar resultado
    print(f"\n[4/4] Guardando metadata actualizada...")
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    # Reporte final
    remaining_unknown = len(pending_ids) - newly_enriched
    print(f"\n{'='*70}")
    print(f"📊 RESUMEN DEL ENRIQUECIMIENTO")
    print(f"{'='*70}")
    print(f"• IDs pendientes antes: {len(pending_ids):,}")
    print(f"• ✅ Nuevos enriquecidos: {newly_enriched:,}")
    print(f"• ❌ Aún sin nombre (fallback): {remaining_unknown:,}")
    print(f"• 📁 Archivo guardado: {METADATA_PATH}")
    print(f"• 📦 Tamaño: {METADATA_PATH.stat().st_size / 1e6:.2f} MB")
    print(f"{'='*70}")
    
    # Ejemplos
    examples = [(sid, meta) for sid, meta in metadata.items() 
                if meta.get("source") == "tracks_csv_enrichment"][:5]
    print(f"\n🎵 EJEMPLOS ENRIQUECIDOS CON tracks.csv:")
    for sid, meta in examples:
        print(f"   • {meta['track_name']} — {meta['artist_name']}")
    
    return True

if __name__ == "__main__":
    success = enrich_from_tracks_csv()
    if success:
        print(f"\n✅ ¡Listo! Reinicia tu servidor Flask para ver los cambios.")
    else:
        print(f"\n❌ Proceso fallido. Revisa los mensajes.")