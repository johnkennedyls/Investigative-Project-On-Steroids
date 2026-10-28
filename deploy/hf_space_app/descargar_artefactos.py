# descargar_artefactos.py - baja los modelos del repo de artefactos al Space
"""
El Space no guarda los 216 MB de pesos en su propio repositorio: viven en un
repo de modelos aparte (por defecto `JohnKLS/echopulse-artifacts`) y se bajan
al arrancar el contenedor.

- Si los ficheros ya están (imagen con artefactos incluidos, o desarrollo
  local), no descarga nada.
- Si el repo no existe o no hay red, falla con un mensaje claro: es mejor un
  error legible que un contenedor que arranca a medias.

Variables:
    ECHOPULSE_ARTIFACTS   repo de modelos (por defecto JohnKLS/echopulse-artifacts)
    HF_TOKEN              solo si el repo de artefactos es privado
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

# Rutas que la app espera, relativas a la raíz del Space
ESPERADOS = [
    "models/song_metadata.json",
    "models/fame_index.parquet",
    "models/tabla_maestra/mst_mr_final.pth",
    "models/tabla_maestra/embeddings.pt",
    "models/talkplay/vocab.json",
    "models/talkplay/song_map.pkl",
    "models/talkplay/intent_model.pth",
    "tabla_maestra/train",
]

REPO = os.getenv("ECHOPULSE_ARTIFACTS", "JohnKLS/echopulse-artifacts").strip()


def _faltantes() -> list[str]:
    faltan = []
    for ruta in ESPERADOS:
        ruta_local = BASE / ruta
        if ruta == "tabla_maestra/train":
            if not any(ruta_local.glob("*.parquet")):
                faltan.append(ruta + "/*.parquet")
        elif not ruta_local.exists():
            faltan.append(ruta)
    return faltan


def main() -> int:
    faltan = _faltantes()
    if not faltan:
        print("✅ Artefactos presentes: no hay nada que descargar.")
        return 0

    print(f"⬇️  Faltan {len(faltan)} artefacto(s) → descargando de «{REPO}»…")
    print("    " + ", ".join(faltan))

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("❌ Falta huggingface_hub. Instala con: pip install huggingface_hub")
        return 1

    token = os.getenv("HF_TOKEN") or None
    try:
        snapshot_download(
            repo_id=REPO,
            repo_type="model",
            local_dir=str(BASE),
            token=token,
            allow_patterns=["models/**", "tabla_maestra/**"],
            max_workers=8,
        )
    except Exception as exc:  # noqa: BLE001 - queremos el motivo tal cual
        print(f"❌ No se pudieron descargar los artefactos de «{REPO}»: {exc}")
        print(
            "   Revisa que el repo exista y sea público, o define la variable\n"
            "   ECHOPULSE_ARTIFACTS=<usuario>/<repo> en Settings → Variables and secrets.\n"
            "   Puedes subir los artefactos con: python deploy/subir_artefactos.py"
        )
        return 1

    faltan = _faltantes()
    if faltan:
        print("❌ Tras la descarga siguen faltando: " + ", ".join(faltan))
        return 1

    print("✅ Artefactos descargados correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
