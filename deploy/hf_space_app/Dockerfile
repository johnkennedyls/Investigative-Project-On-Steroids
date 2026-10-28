# EchoPulse AI — imagen para Hugging Face Spaces (Docker, CPU)
#
# Qué hace este Dockerfile:
#   1. Python 3.12 liviano + dependencias (Flask, pandas, sklearn…)
#   2. PyTorch CPU aparte, desde el índice oficial de CPU (pesa ~10x menos que CUDA)
#   3. Copia el código del agente y arranca `start.sh`, que descarga los modelos
#      (repo de artefactos) y lanza gunicorn en el puerto 7860 que exige Spaces.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860 \
    TABLA_MAESTRA_DIR=/app/tabla_maestra/train \
    OLLAMA_ENABLED=0 \
    HF_HOME=/tmp/huggingface

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt \
    && python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0

COPY . .
# Hijos de Spaces suele ejecutar el contenedor como UID 1000: hay que darle
# permiso de escritura en /app para descargar los artefactos y escribir logs.
RUN mkdir -p /app/logs \
    && chown -R 1000:1000 /app \
    && chmod -R u+w /app

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

CMD ["bash", "start.sh"]
