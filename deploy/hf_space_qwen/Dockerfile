# Qwen gratis en Hugging Face Spaces (CPU básica, sin créditos)
#
# La imagen oficial de llama.cpp ya trae `llama-server`, que expone una API
# compatible OpenAI (/v1/chat/completions). `-hf` descarga el GGUF del repo
# oficial de Qwen en Hugging Face al arrancar el contenedor.
#
# El modelo se puede cambiar SIN tocar este archivo: crea en el Space la
# variable `MODELO` (Settings -> Variables and secrets) con otro repo GGUF.
# Ejemplos:
#   Qwen/Qwen2.5-1.5B-Instruct-GGUF:Q4_K_M   (rápido en 2 vCPU, ~1 GB)
#   Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M     (mejor calidad, ~1.9 GB)
FROM ghcr.io/ggml-org/llama.cpp:server

# LLAMA_CACHE: dónde cachea llama.cpp el GGUF. /tmp es escribible siempre,
# incluso si el contenedor corre con un usuario sin privilegios (UID 1000).
ENV MODELO="Qwen/Qwen2.5-1.5B-Instruct-GGUF:Q4_K_M" \
    CONTEXTO=4096 \
    HILOS=2 \
    PUERTO=7860 \
    LLAMA_CACHE=/tmp/llama-cache

EXPOSE 7860

# --host 0.0.0.0 para que Spaces pueda enrutar el puerto 7860.
# --parallel 1: una sola conversación a la vez (2 vCPU, no hay para más).
CMD ["sh", "-c", "mkdir -p ${LLAMA_CACHE} && llama-server -hf ${MODELO} --host 0.0.0.0 --port ${PUERTO} -c ${CONTEXTO} -t ${HILOS} --parallel 1"]
