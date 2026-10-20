# Qwen gratis en Hugging Face Spaces (CPU básica, sin créditos)
#
# La imagen oficial de llama.cpp ya trae el servidor con API compatible OpenAI.
# `-hf` descarga el GGUF del repo oficial de Qwen en Hugging Face la primera vez.
FROM ghcr.io/ggml-org/llama.cpp:server

ENV MODELO="Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M" \
    CONTEXTO=4096 \
    HILOS=2 \
    PUERTO=7860

EXPOSE 7860

# --host 0.0.0.0 para que Spaces pueda enrutar el puerto 7860.
CMD ["sh", "-c", "llama-server -hf ${MODELO} --host 0.0.0.0 --port ${PUERTO} -c ${CONTEXTO} -t ${HILOS} --parallel 1"]
