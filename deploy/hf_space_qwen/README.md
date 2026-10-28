---
title: EchoPulse Qwen Gratis
emoji: 🎵
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
short_description: Qwen con llama.cpp para EchoPulse AI
---

# Qwen gratis para EchoPulse (Hugging Face Space)

Este Space expone **Qwen2.5** (GGUF del repo oficial de Hugging Face) con la API
compatible OpenAI de `llama.cpp`. Corre en el hardware **gratuito** de Spaces
(CPU basic, 2 vCPU, 16 GB), sin créditos de Inference Providers.

## Qué devuelve

- `POST /v1/chat/completions` — chat compatible OpenAI (lo consume
  `echopulse_llm_orquestator/llm_client.py`).
- `GET /health` — estado del servidor (devuelve `{"status":"ok"}` cuando cargó).
- `GET /v1/models` — lista de modelos.

## Modelo

Por defecto `Qwen/Qwen2.5-1.5B-Instruct-GGUF:Q4_K_M` (~1 GB, el más ágil en
2 vCPU). Para cambiarlo **no hace falta tocar el Dockerfile**: crea en el Space
una variable `MODELO` (Settings → Variables and secrets):

| `MODELO` | Tamaño | Nota |
|---|---|---|
| `Qwen/Qwen2.5-1.5B-Instruct-GGUF:Q4_K_M` | ~1 GB | por defecto, respuestas en 5-15 s |
| `Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M` | ~1,9 GB | mejor calidad, más lento |
| `Qwen/Qwen2.5-0.5B-Instruct-GGUF:Q4_K_M` | ~0,4 GB | solo para pruebas |

El GGUF se descarga al arrancar el contenedor y se cachea en `/tmp/llama-cache`
durante la vida del Space. **Cold start**: 2-4 minutos la primera vez
(descarga + carga); después, unos segundos.

## Conectarlo al agente

En el Space de la app (`echopulse-ai`), Settings → Variables:

```env
LLM_BASE_URL=https://<tu-usuario>-<este-space>.hf.space/v1
LLM_MODEL=qwen
```

Luego comprueba desde la app:

```bash
curl -X POST https://<tu-usuario>-echopulse-ai.hf.space/api/llm/probar
```

Debe responder `"proveedor": "custom"`.

> La URL exacta está en el menú **⋮ → Embed this Space** de este Space.

## Aviso de rendimiento

En CPU básica, Qwen2.5-1.5B responde a unas 10-15 palabras por segundo: una
respuesta de 3 frases tarda 5-15 s. Es suficiente para la demo, pero si
necesitas respuestas instantáneas usa Groq (Qwen3-32B) como voz del agente.
