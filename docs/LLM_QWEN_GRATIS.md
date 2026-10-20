# Voz de EchoPulse: Qwen gratis (sin créditos de Hugging Face)

> Documento técnico del cambio en la capa LLM del orquestador.
> Código: `echopulse_llm_orquestator/llm_client.py` y `conversacion.py`.

---

## 1. Diagnóstico del error de Hugging Face

Los logs mostraban dos errores distintos que parecían el mismo:

| Código | Mensaje real del router | Causa |
|---|---|---|
| `400 Bad Request` | el cuerpo se descartaba (`raise_for_status`) | el modelo `Qwen/Qwen2.5-7B-Instruct` ya no está publicado en el router |
| `402 Payment Required` | `You have no remaining credits. Purchase pre-paid credits to continue using Inference Providers. Alternatively, subscribe to PRO to get monthly included credits.` | Hugging Face pasó a **Inference Providers prepago**: sin créditos no hay inferencia |

Comprobaciones hechas sobre la cuenta del proyecto:

```console
$ curl -H "Authorization: Bearer $HF_TOKEN" https://huggingface.co/api/whoami-v2
{"name":"JohnKLS", "canPay":false, "billingMode":"prepaid", "isPro":false, ...}

$ curl -H "Authorization: Bearer $HF_TOKEN" \
       https://router.huggingface.co/v1/models
# 137 modelos; ninguno de los 30 modelos Qwen ofrece un proveedor con is_free: true
```

Conclusión: **el router de Hugging Face no tiene Qwen gratis**. No es un bug
de la app ni del token; es el modelo de cobro. Además el cliente anterior tenía
dos defectos propios:

1. Reintentaba 3 veces cualquier error (incluido el 402), gastando ~8 s por
   turno antes de rendirse.
2. `raise_for_status()` ocultaba el JSON de error, así que solo se veía
   `400 Client Error` sin la explicación.

Ambos están corregidos en `llm_client.py`.

---

## 2. Cómo quedó la arquitectura de voz

```
app.py (Fase 1 intención · Fase 4 respuesta)
        │  messages[] con historial real
        ▼
  llm_client.ClienteLLM
        │  prueba en orden y salta los proveedores caídos
        ├─ 1. LLM_BASE_URL  → cualquier endpoint compatible OpenAI
        │                     (HF Space propio, Groq, DashScope, vLLM…)
        ├─ 2. Ollama local  → Qwen desde un GGUF oficial de Hugging Face
        ├─ 3. Router HF     → solo si la cuenta tiene créditos
        ▼
  conversacion.py
        ├─ prompts (intención y charla)
        └─ motor determinista (si no hay ningún LLM disponible)
```

Comportamiento ante errores (antes → ahora):

| Situación | Antes | Ahora |
|---|---|---|
| `402` sin créditos | 3 reintentos (~8 s) por fase | se marca caído 6 h, 1 sola llamada |
| `400` modelo inexistente | 3 reintentos | se marca caído 10 min |
| `429` / `5xx` | 3 reintentos ciegos | 1 reintento si `Retry-After` ≤ 5 s |
| Sin ningún LLM | frase enlatada | respuesta conversacional determinista |

`GET /api/health` ahora dice la verdad desde el arranque: al iniciar se hace un
ping de 1 token a cada proveedor y los 402 se reportan con su motivo.

```json
"llm": {
  "orden": ["hf", "ollama"],
  "disponibles": ["ollama"],
  "caidos": {"hf": {"motivo": "HTTP 402: You have no remaining credits...", "queda_s": 21580}},
  "ultimo_ok": {"proveedor": "ollama", "modelo": "qwen2.5:1.5b-instruct-q4_K_M"}
}
```

---

## 3. Opciones para usar Qwen gratis

| Opción | Coste | Requisitos | Calidad | Latencia en CPU |
|---|---|---|---|---|
| **A. Ollama local** con GGUF oficial de HF | 0 | ~1-2 GB de disco | Qwen2.5 1.5B/3B | 3-8 s por respuesta |
| **B. Hugging Face Space propio** (`deploy/hf_space_qwen`) | 0 | cuenta HF | Qwen2.5 3B | 10-20 s por respuesta |
| **C. Groq free** (`qwen/qwen3-32b`) | 0 | key gratis | Qwen3 32B | < 2 s |
| **D. Alibaba ModelStudio** (`qwen-plus`) | 0 (cuota de prueba) | key gratis | Qwen Plus | 2-4 s |
| Router HF con créditos | pago | PRO o prepago | cualquiera | 1-3 s |

### A. Ollama local (recomendada para desarrollar y para la demo)

```bash
# Opción 1: el GGUF oficial de Qwen en Hugging Face
ollama pull hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M

# Opción 2: el catálogo de Ollama (mismo modelo, más rápido de bajar)
ollama pull qwen2.5:3b-instruct-q4_K_M
```

No hace falta configurar nada: `llm_client.py` autodetecta el mejor Qwen
instalado (prefiere `instruct` y el más grande hasta 4B). Para fijarlo:

```env
OLLAMA_MODEL=qwen2.5:3b-instruct-q4_K_M
```

### B. Hugging Face Space propio (recomendada para desplegar)

La carpeta [`deploy/hf_space_qwen`](../deploy/hf_space_qwen) contiene un Space
Docker mínimo que sirve `Qwen/Qwen2.5-3B-Instruct-GGUF` con la API compatible
OpenAI de `llama.cpp`, en el hardware **gratuito** de Spaces.

```bash
# 1. crea el Space (Docker, CPU basic) desde la web de HF y luego:
git clone https://huggingface.co/spaces/<usuario>/<space>
cp deploy/hf_space_qwen/{Dockerfile,README.md} <space>/
cd <space> && git add . && git commit -m "Qwen gratis" && git push
```

Cuando el Space esté "Running", apunta el agente a su `/v1`:

```env
LLM_BASE_URL=https://<usuario>-<space>.hf.space/v1
LLM_MODEL=qwen
```

### C. Groq (nube gratis, la más rápida)

```env
GROQ_API_KEY=gsk_...
GROQ_MODEL=qwen/qwen3-32b
```

### D. Alibaba ModelStudio / DashScope

```env
DASHSCOPE_API_KEY=sk-...
DASHSCOPE_MODEL=qwen-plus
```

> El orden de intentos se controla con `LLM_ORDER` (por defecto
> `custom,groq,dashscope,openrouter,hf,ollama`).

---

## 4. Configuración

Copia `echopulse_llm_orquestator/.env.example` a `.env`. Lo mínimo para Ollama
local es **no poner nada**: el cliente lo detecta en `http://127.0.0.1:11434`.

Variables nuevas:

| Variable | Uso | Defecto |
|---|---|---|
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | endpoint propio compatible OpenAI | – |
| `OLLAMA_MODEL` | fija el Qwen local | autodetectado |
| `OLLAMA_KEEP_ALIVE` | minutos que el modelo sigue en RAM | `30m` |
| `LLM_ORDER` | orden de proveedores | `custom,groq,dashscope,openrouter,hf,ollama` |
| `INTENT_MODE` | `auto` / `llm` / `heuristica` | `auto` |
| `LLM_MAX_TOKENS_CHAT` | longitud máxima de la respuesta | `160` |
| `LLM_TEMPERATURA_CHAT` | creatividad de la charla | `0.7` |

`INTENT_MODE=auto` significa: la Fase 1 usa la heurística ES→EN y solo consulta
al modelo cuando el mensaje es una pregunta, pide "más de lo mismo" o no tiene
tono reconocible. Así se ahorra una llamada al LLM en la mayoría de turnos.

---

## 5. Verificación

```bash
# 1. pruebas sin red ni modelos (402, 429, limpieza de  thinking, motor determinista)
python scripts/test_llm.py

# 2. estado real de la cadena
curl http://localhost:5000/api/health
curl http://localhost:5000/api/llm/status

# 3. prueba de fuego: quién responde y en cuánto
curl -X POST http://localhost:5000/api/llm/probar

# 4. conversación simulada de 5 turnos (usuario simulado por el propio Qwen)
python scripts/simular_conversacion.py --turnos 5
```

---

## 6. Cómo el LLM "emula" una conversación

Antes cada fase era una llamada aislada con el historial aplanado en un string.
Ahora:

1. **Historial como turnos reales.** `conversacion.construir_mensajes()` arma
   `[system] + últimos 8 turnos (user/assistant) + turno actual`, que es lo que
   Qwen espera para comportarse como un chat.
2. **Memoria de sesión** (`CONVERSACIONES`):
   - `recomendados`: IDs ya ofrecidos → el retrieval no repite canciones;
   - `ultima_query_en`: vibe actual → "dame otras parecidas" sigue la línea;
   - `ultimos_nombres`: últimas canciones → se le prohíbe al modelo repetirlas;
   - `turnos`: cambia la apertura y la pregunta de cierre en cada turno.
3. **El sistema le pide reaccionar antes de recomendar**, responder preguntas
   del usuario y cerrar con una pregunta distinta cada vez.
4. **Salvaguardas para modelos pequeños** (`conversacion.garantizar_canciones`):
   recorta a 5 frases y, si el modelo no citó ninguna canción real, añade dos
   del catálogo. Evita que un 0.5B invente títulos.
5. **Motor determinista** cuando no hay ningún LLM: detecta tono y tipo de turno
   (saludo, pregunta, "más de lo mismo", feedback) y responde citando canciones
   reales, sin la frase enlatada que empezaba con "Además…" en el primer turno.

---

## 7. Rendimiento medido

Equipo de prueba: Intel i5-7200U (2 núcleos / 4 hilos), CPU, 8 GB RAM.
Latencia del turno completo = Fase 1 + Módulo 2 + Módulo 3 + Fase 4.

| Motor | Respuesta del LLM | Turno completo | Observación |
|---|---|---|---|
| Sin LLM (determinista) | 0 ms | **0,3 s** | respaldo; cita canciones reales |
| Qwen2.5-0.5B Q4 (Ollama) | 3-4 s | 6-8 s | divaga, ignora la lista |
| Qwen2.5-1.5B Q4 (Ollama) | 6-15 s | 10-16 s | conversa bien; alucina títulos a veces (se filtran) |
| Qwen2.5-3B Q4 | — | — | no medido: el GGUF no terminó de descargar aquí |
| Router HF | — | — | inutilizable sin créditos (402) |

Con el cliente anterior, cada turno perdía además ~8 s en tres reintentos de
402 y terminaba en una frase enlatada. Ahora el 402 se detecta en la primera
llamada (~1 s) y el turno sigue con el siguiente proveedor.

Calidad del 1.5B en la simulación de 5 turnos: 5/5 respuestas citaron una
canción real del catálogo, 5/5 cerraron con pregunta, 50 canciones distintas y
0 repeticiones entre turnos.


---

## 8. Limitaciones conocidas

- En CPU de 2 núcleos, un 3B responde a ~3-4 palabras/s: para la demo en vivo
  conviene 1.5B o un Space con más CPU.
- Los Spaces gratuitos se duermen: el primer mensaje tras la inactividad tarda
  en despertar (~1-2 min, incluida la descarga del GGUF si no hay caché).
- El motor determinista es un respaldo, no un sustituto: no razona, solo
  clasifica tono/intención y compone la respuesta.
- El `--usuario llm` de `scripts/simular_conversacion.py` necesita un modelo
  ≥7B: un 1.5B copia al asistente en vez de hacer de usuario. Para demos en CPU
  se usa `--usuario guion` (por defecto).
- Fuera del alcance de este cambio: el retrieval (Módulo 2) prioriza similitud
  lírica, así que "triste" puede devolver canciones pop. Es un tema del modelo
  de embeddings, no de la capa LLM.

