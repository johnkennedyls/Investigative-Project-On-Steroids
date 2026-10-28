---
title: EchoPulse AI
emoji: 🎧
colorFrom: indigo
colorTo: cyan
sdk: docker
app_port: 7860
pinned: false
short_description: Recomendador musical conversacional (Módulos 2 y 3)
---

# 🎧 EchoPulse AI — orquestador conversacional

Recomendador musical que conversa: entiende el mood del usuario, recupera
canciones de la Tabla Maestra (Módulo 2, MST-MR Transformer), las reordena por
intención (Módulo 3, IntentTransformer) y responde con Qwen.

## Cómo está montado

- **Este Space**: la app Flask (retrieval + re-ranking + chat).
- **Repo de artefactos** (`ECHOPULSE_ARTIFACTS`, por defecto
  `JohnKLS/echopulse-artifacts`): los 216 MB de pesos y datos que se descargan
  al arrancar.
- **Space de Qwen** (opcional): `deploy/hf_space_qwen`, se conecta con
  `LLM_BASE_URL=https://<usuario>-<space>.hf.space/v1`.

## Variables y secretos

| Nombre | Tipo | Para qué |
|---|---|---|
| `ECHOPULSE_ARTIFACTS` | Variable | repo de modelos (por defecto `JohnKLS/echopulse-artifacts`) |
| `LLM_BASE_URL` | Variable | endpoint OpenAI-compatible del Space de Qwen |
| `LLM_MODEL` | Variable | nombre del modelo (en llama.cpp da igual, p. ej. `qwen`) |
| `GROQ_API_KEY` | **Secret** | alternativa rápida a Qwen local (Qwen3-32B) |
| `HF_TOKEN` | **Secret** | solo si el repo de artefactos es privado |

Sin ninguna de las variables de voz, la app responde igual con el motor
conversacional determinista (modo degradado).

## Enlaces

- `/` chat
- `/api/health` estado de módulos y de la cadena LLM
- `/api/llm/status`, `POST /api/llm/probar` diagnóstico de la voz
