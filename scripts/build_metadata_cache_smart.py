# build_metadata_cache_smart.py
"""
Script Detective: Encuentra la columna correcta en el parquet para mapear
los IDs de song_map.pkl y genera el cache de metadatos.
"""
import pandas as pd
import pickle
import json
from pathlib import Path

# =====================================================================
# 1. CONFIGURACIÓN DE RUTAS
# =====================================================================
BASE_DIR = Path(__file__).parent
SONG_MAP_PATH = BASE_DIR / "echopulse_llm_orquestator" / "models" / "talkplay" / "song_map.pkl"
PARQUET_PATH = BASE_DIR / "tabla_maestra" / "train" / "part-00000-0cbbc0cd-4603-4851-afb0-2f9a0fa6eb89-c000.snappy.parquet"
OUTPUT_PATH = BASE_DIR / "echopulse_llm_orquestator" / "models" / "song_metadata.json"

# =====================================================================
# 2. CARGA DE DATOS
# =====================================================================
print("🔍 Cargando datos...")

# Cargar IDs del modelo
with open(SONG_MAP_PATH, 'rb') as f:
    song_map = pickle.load(f)
model_ids = set(song_map.keys())
print(f"📦 Modelo tiene {len(model_ids):,} IDs únicos.")

# Cargar Parquet
df = pd.read_parquet(PARQUET_PATH)
print(f"📊 Parquet tiene {len(df):,} filas y {len(df.columns)} columnas.")

# =====================================================================
# 3. DETECCIÓN DE COLUMNA CLAVE
# =====================================================================
print("\n🔎 Escaneando columnas para encontrar la que coincide con los IDs del modelo...")
matches = {}

for col in df.columns:
    # Convertir a string para asegurar comparación (evita errores de tipo int vs str)
    col_values = set(df[col].astype(str).unique())
    
    # Intersección: IDs que existen en AMBOS lados
    overlap = len(model_ids & col_values)
    matches[col] = overlap

# Ordenar resultados
sorted_matches = sorted(matches.items(), key=lambda x: x[1], reverse=True)

print("\n📈 TOP 3 Columnas con más coincidencias:")
for col, count in sorted_matches[:3]:
    print(f"   • {col}: {count:,} coincidencias ({100*count/len(df):.1f}%)")

# Seleccionar la mejor
best_col, best_count = sorted_matches[0]

if best_count < 100:
    print("\n⚠️ ADVERTENCIA: Pocas coincidencias (<100).")
    print("   Es probable que tu parquet no tenga los mismos IDs que el modelo.")
    print("   Se intentará usar la mejor opción disponible, pero los enlaces pueden ser de búsqueda.")

# =====================================================================
# 4. GENERACIÓN DE CACHE
# =====================================================================
print(f"\n🔗 Usando columna '{best_col}' para mapear...")

# Indexar el dataframe por la columna clave
# Nota: Si la columna tiene duplicados, tomamos el primero
df_indexed = df.set_index(best_col).astype(str)

metadata = {}
# Detectar columnas de texto
def get_col(patterns):
    for p in patterns:
        for c in df.columns:
            if p.lower() in c.lower():
                return c
    return None

track_col = get_col(['track_title', 'name']) or 'track_title'
artist_col = get_col(['artist_name', 'artist']) or 'artist_name'
genre_col = get_col(['genre_lyr', 'genre']) or 'genre_lyr'

# Construir diccionario
# Iteramos sobre las IDs que SÍ coinciden para no inflar el archivo innecesariamente
valid_ids = set(df[best_col].astype(str)) & model_ids

print(f"🏗️ Generando metadatos para {len(valid_ids)} canciones...")

count = 0
for song_id in valid_ids:
    if song_id in df_indexed.index:
        row = df_indexed.loc[song_id]
        metadata[song_id] = {
            "track_name": row.get(track_col, "Unknown").strip(),
            "artist_name": row.get(artist_col, "Unknown").strip(),
            "genre": row.get(genre_col, "Unknown").strip() if genre_col in df.columns else "Unknown",
            "source_column": best_col # Guardamos de dónde vino para debug
        }
        count += 1

# Guardar
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(metadata, f, indent=2, ensure_ascii=False)

print(f"\n✅ ¡Listo! Cache guardado en {OUTPUT_PATH}")
print(f"📊 Resumen: {count} canciones con metadatos.")
print(f"💡 Siguiente paso: Ejecuta python app.py")