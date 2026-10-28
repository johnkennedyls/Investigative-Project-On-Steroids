# subir_artefactos.py - sube los pesos y datos a un repo de modelos de Hugging Face
"""
El Space de la app NO lleva los 216 MB de pesos en su repositorio: se suben una
sola vez a un repo de modelos y el Space los descarga al arrancar.

Requisitos (una vez):
    pip install huggingface_hub
    hf auth login          # o define HUGGINGFACE_HUB_TOKEN

Uso:
    python deploy/subir_artefactos.py
    python deploy/subir_artefactos.py --repo mi-usuario/echopulse-artifacts
    python deploy/subir_artefactos.py --dry-run      # solo lista lo que subiría
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
AGENTE = RAIZ / "echopulse_llm_orquestator"

# (ruta local, ruta dentro del repo de modelos)
ARCHIVOS = [
    (AGENTE / "models" / "song_metadata.json", "models/song_metadata.json"),
    (AGENTE / "models" / "fame_index.parquet", "models/fame_index.parquet"),
    (AGENTE / "models" / "tabla_maestra" / "mst_mr_final.pth", "models/tabla_maestra/mst_mr_final.pth"),
    (AGENTE / "models" / "tabla_maestra" / "embeddings.pt", "models/tabla_maestra/embeddings.pt"),
    (AGENTE / "models" / "talkplay" / "vocab.json", "models/talkplay/vocab.json"),
    (AGENTE / "models" / "talkplay" / "song_map.pkl", "models/talkplay/song_map.pkl"),
    (AGENTE / "models" / "talkplay" / "intent_model.pth", "models/talkplay/intent_model.pth"),
]

TARJETA = """---
tags:
  - music-recommendation
  - echopulse
---

# EchoPulse AI — artefactos

Pesos y datos que usa el Space [`{space}`] para recomendar música:

| Ruta | Qué es |
|---|---|
| `models/tabla_maestra/mst_mr_final.pth` | Módulo 2 (MST-MR Transformer) + scaler |
| `models/tabla_maestra/embeddings.pt` | embeddings de las canciones de la tabla maestra |
| `models/talkplay/intent_model.pth` | Módulo 3 (IntentTransformer) |
| `models/talkplay/song_map.pkl` | mapa Spotify ID → clase del Módulo 3 |
| `models/talkplay/vocab.json` | vocabulario del Módulo 3 |
| `models/song_metadata.json` | metadatos (nombre, artista, género, popularidad) |
| `models/fame_index.parquet` | señal de fama por artista/canción |
| `tabla_maestra/train/*.parquet` | tabla maestra de entrenamiento (retrieval) |

Se generan con los notebooks de `docs/` y `scripts/build_metadata_cache.py` /
`scripts/build_fame_index.py` del repositorio del proyecto.
"""


def tamano_mb(ruta: Path) -> float:
    return ruta.stat().st_size / 1048576


def main() -> int:
    parser = argparse.ArgumentParser(description="Sube los artefactos de EchoPulse a Hugging Face")
    parser.add_argument("--repo", default="JohnKLS/echopulse-artifacts", help="usuario/nombre del repo de modelos")
    parser.add_argument("--space", default="JohnKLS/echopulse-ai", help="Space que los consume (para la tarjeta)")
    parser.add_argument("--dry-run", action="store_true", help="solo listar archivos y tamaños")
    args = parser.parse_args()

    # 1) La tabla maestra: se coge el .parquet de train (puede haber varios)
    parquets = sorted((RAIZ / "tabla_maestra" / "train").glob("*.parquet"))
    if not parquets:
        print("❌ No hay .parquet en tabla_maestra/train")
        return 1
    pares = list(ARCHIVOS) + [(p, f"tabla_maestra/train/{p.name}") for p in parquets]

    # 2) Comprobar que existen y sumar tamaños
    total = 0.0
    for local, remoto in pares:
        if not local.exists():
            print(f"❌ Falta {local}")
            return 1
        mb = tamano_mb(local)
        total += mb
        print(f"   {mb:8.2f} MB  {remoto}")

    print(f"\n   TOTAL: {total:.2f} MB → repo «{args.repo}»")
    if args.dry_run:
        print("(dry-run: no se sube nada)")
        return 0

    try:
        from huggingface_hub import HfApi, create_repo
    except ImportError:
        print("❌ Falta huggingface_hub: pip install huggingface_hub")
        return 1

    api = HfApi()
    try:
        usuario = api.whoami()["name"]
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Sin sesión en Hugging Face: {exc}")
        print("   Ejecuta:  hf auth login   (o exporta HUGGINGFACE_HUB_TOKEN)")
        return 1

    print(f"👤 Sesión: {usuario}")
    create_repo(args.repo, repo_type="model", exist_ok=True, private=False)
    print(f"📦 Repo listo: https://huggingface.co/{args.repo}")

    for local, remoto in pares:
        print(f"⬆️  {remoto} …", end="", flush=True)
        api.upload_file(path_or_fileobj=str(local), path_in_repo=remoto, repo_id=args.repo)
        print(" ok")

    api.upload_file(
        path_or_fileobj=TARJETA.format(space=args.space).encode("utf-8"),
        path_in_repo="README.md",
        repo_id=args.repo,
    )

    print(f"\n✅ Listo. Pon en el Space la variable ECHOPULSE_ARTIFACTS={args.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
