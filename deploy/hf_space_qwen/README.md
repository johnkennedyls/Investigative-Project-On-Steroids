---
title: EchoPulse Qwen Gratis
emoji: 🎵
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Qwen gratis para EchoPulse (Hugging Face Space)

Este Space expone **Qwen2.5-3B-Instruct** (GGUF Q4_K_M, el repo oficial
`Qwen/Qwen2.5-3B-Instruct-GGUF` de Hugging Face) con la API compatible OpenAI
de `llama.cpp`. Corre en el hardware **gratuito** de Spaces (CPU basic, 2 vCPU,
16 GB), sin créditos de Inference Providers.

## Qué devuelve

- `POST /v1/chat/completions` — chat compatible OpenAI (es lo que consume
  `echopulse_llm_orquestator/llm_client.py`).
- `GET /health` — estado del servidor.
- `GET /v1/models` — lista de modelos.

La primera vez descarga ~1,9 GB del modelo; luego queda cacheado mientras el
Space siga despierto (los Spaces gratis se duermen por inactividad y al volver
tardan un par de minutos en recargar).

## Conectarlo al agente

En `echopulse_llm_orquestator/.env`:

```env
LLM_BASE_URL=https://<usuario>-<nombre-del-space>.hf.space/v1
LLM_API_KEY=
LLM_MODEL=qwen
```

Luego `python app.py` y comprueba con:

```bash
curl -X POST http://localhost:5000/api/llm/probar
```

## Aviso de rendimiento

En CPU básica, Qwen2.5-3B responde a unas pocas palabras por segundo: una
respuesta de 3 frases puede tardar 10-20 s. Para una demo rápida conviene
probar `Qwen2.5-1.5B-Instruct-GGUF` (cambiando la variable `MODELO` del
`Dockerfile`).
