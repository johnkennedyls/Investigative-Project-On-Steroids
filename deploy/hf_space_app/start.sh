#!/usr/bin/env bash
# Arranque del Space: modelos + gunicorn.
set -euo pipefail

PUERTO="${PORT:-7860}"

echo "=============================================================="
echo "🎧 EchoPulse AI — arranque en Hugging Face Spaces"
echo "   puerto: ${PUERTO}"
echo "   artefactos: ${ECHOPULSE_ARTIFACTS:-JohnKLS/echopulse-artifacts}"
if [ -n "${LLM_BASE_URL:-}" ]; then
    echo "   voz: endpoint compatible OpenAI → ${LLM_BASE_URL}"
elif [ -n "${GROQ_API_KEY:-}" ]; then
    echo "   voz: Groq (Qwen3-32B)"
else
    echo "   voz: sin LLM externo → respuestas deterministas"
fi
echo "=============================================================="

# 1) Bajar los modelos (si ya están en la imagen, el script no hace nada)
python descargar_artefactos.py

# 2) Servir la app. Un worker y varios hilos: los modelos ya ocupan RAM y se
#    comparten entre peticiones; --timeout alto porque la respuesta del LLM
#    en CPU puede tardar 30-60 s.
exec gunicorn app:app \
    --bind "0.0.0.0:${PUERTO}" \
    --workers 1 \
    --threads 4 \
    --timeout 300 \
    --graceful-timeout 30 \
    --access-logfile - \
    --error-logfile -
