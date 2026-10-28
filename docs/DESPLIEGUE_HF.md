# Desplegar EchoPulse AI en Hugging Face Spaces

Guía para quien nunca ha desplegado nada. Al terminar vas a tener una URL
pública tipo `https://tu-usuario-echopulse-ai.hf.space` con el agente
funcionando, y otra con Qwen gratis.

---

## 0. Qué vas a desplegar (y por qué son 3 piezas)

```
┌────────────────────────────┐        ┌─────────────────────────────┐
│  Space 1: echopulse-qwen   │        │  Space 2: echopulse-ai      │
│  llama.cpp + Qwen 1.5B/3B  │◀───────│  Flask: Módulo 2 + Módulo 3 │
│  (la "voz")                │  HTTP  │  + chat + interfaz web      │
│  URL …-echopulse-qwen.hf…  │        │  URL …-echopulse-ai.hf.space│
└────────────────────────────┘        └──────────────┬──────────────┘
                                                     │ descarga al arrancar
                                                     ▼
                                      ┌─────────────────────────────┐
                                      │  Repo de modelos            │
                                      │  tu-usuario/echopulse-      │
                                      │  artifacts  (216 MB)        │
                                      └─────────────────────────────┘
```

| Pieza | Qué es | Por qué separada |
|---|---|---|
| **Repo de artefactos** | Un repo de *modelos* de HF con los pesos (`.pth`, `.pt`, `.pkl`, `.parquet`) | Los Space pesan poco y se reconstruyen rápido; los pesos se suben una vez |
| **Space de la app** | Contenedor Docker con tu Flask | Es lo que el usuario visita |
| **Space de Qwen** | Contenedor con `llama-server` + Qwen | Se reinicia/actualiza sin tocar la app; si está dormido, la app sigue respondiendo en modo determinista |

Conceptos mínimos:

- **Space** = un contenedor Docker alojado por Hugging Face con una URL pública.
- **Build** = HF construye la imagen desde tu `Dockerfile` cada vez que haces `git push`. Tarda minutos.
- **Runtime** = el contenedor corriendo; ahí se descargan los pesos y se cargan los modelos.
- **Variables** = configuración visible (p. ej. `LLM_BASE_URL`).
- **Secrets** = igual, pero ocultos (tokens, API keys).
- **Sleep** = los Spaces gratis se duermen tras un rato sin visitas; el primer acceso los despierta.

Plan gratis: **CPU basic** = 2 vCPU, 16 GB RAM, 50 GB de disco, sin GPU.
Suficiente para este proyecto.

---

## 1. Antes de empezar

Necesitas:

- Cuenta en [huggingface.co](https://huggingface.co) (verificada por email).
- `git` instalado (ya lo tienes, el proyecto está en un repo).
- Python con `huggingface_hub` actualizado:

```powershell
pip install -U huggingface_hub
```

- ~250 MB de subida disponibles y paciencia la primera vez (la subida de los
  pesos es lo que más tarda).

Comprueba que el proyecto está listo:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\preparar_space_app.ps1
```

Eso crea `build\hf_space_app` con exactamente lo que va a llevar el Space
(código + Dockerfile + arranque, **sin** los 216 MB de pesos).

---

## 2. Autenticarte en Hugging Face

1. Entra a <https://huggingface.co/settings/tokens>.
2. **Create new token** → tipo **Write** (no "Read").
3. Copia el token (`hf_...`), no se vuelve a mostrar.

En la terminal:

```powershell
hf auth login
```

Pega el token cuando lo pida. Verifica:

```powershell
hf auth whoami
```

Debe imprimir tu usuario. Si `hf` no existe, usa `huggingface-cli login`.

> El token se guarda en `%USERPROFILE%\.cache\huggingface\token`. Git lo usará
> también como contraseña si clonas por HTTPS.

---

## 3. Subir los artefactos (216 MB) — una sola vez

Primero míralos sin subir nada:

```powershell
python deploy\subir_artefactos.py --dry-run
```

Debe listar 8 ficheros y un total de ~216 MB. Ahora súbelos:

```powershell
python deploy\subir_artefactos.py --repo tu-usuario/echopulse-artifacts
```

Qué hace:

1. Crea el repo de modelos `tu-usuario/echopulse-artifacts` (público).
2. Sube cada fichero con `huggingface_hub` (usa LFS automáticamente).
3. Escribe un `README.md` (tarjeta del repo).

Verifica en <https://huggingface.co/tu-usuario/echopulse-artifacts/tree/main>:
deben aparecer `models/` y `tabla_maestra/train/`.

> Si prefieres el repo **privado**: crea el repo a mano con visibilidad
> privada, sube con `--repo` y luego guarda `HF_TOKEN` como **Secret** en el
> Space de la app.

---

## 4. Crear el Space de Qwen (la voz)

### 4.1 Crear el Space

1. Entra a <https://huggingface.co/new-space>.
2. Rellena:
   - **Owner**: tu usuario.
   - **Space name**: `echopulse-qwen`.
   - **License**: la que uses (p. ej. MIT).
   - **Select the Space SDK**: **Docker** → *Blank*.
   - **Hardware**: **CPU basic · 2 vCPU · 16 GB · FREE**.
   - **Visibility**: Public.
3. **Create Space**.

### 4.2 Subir los dos ficheros

```powershell
git clone https://huggingface.co/spaces/tu-usuario/echopulse-qwen
cd echopulse-qwen
copy ..\echopulse_llm_orquestator\..\deploy\hf_space_qwen\Dockerfile .
copy ..\deploy\hf_space_qwen\README.md .
git add .
git commit -m "Qwen gratis con llama.cpp"
git push
```

> Cuando git pida contraseña, pega el token `hf_...` (usuario: tu usuario HF).

### 4.3 Esperar el build

En la pestaña **Logs** del Space verás `Building` → `Running`. La primera vez
tarda unos minutos. Cuando arranque, `llama-server` descarga el GGUF (~1 GB) y
queda escuchando en el puerto 7860.

### 4.4 Probar que responde

Sustituye `<tu-usuario>`:

```powershell
curl https://<tu-usuario>-echopulse-qwen.hf.space/v1/models
```

Y una prueba de chat:

```powershell
curl -X POST https://<tu-usuario>-echopulse-qwen.hf.space/v1/chat/completions `
  -H "Content-Type: application/json" `
  -d '{\"model\":\"qwen\",\"messages\":[{\"role\":\"user\",\"content\":\"hola\"}],\"max_tokens\":20}'
```

### 4.5 Cambiar de modelo sin tocar el Dockerfile

Settings → **Variables and secrets** → New variable:

| Nombre | Valor |
|---|---|
| `MODELO` | `Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M` (mejor calidad, más lento) |

Por defecto usa `Qwen/Qwen2.5-1.5B-Instruct-GGUF:Q4_K_M` (~1 GB, más rápido en
2 vCPU). Guardar la variable reinicia el Space.

> **Truco para la demo**: antes de presentar, abre la URL del Space de Qwen
> para despertarlo. Si está dormido, la app responderá con el motor
> determinista (funciona, pero sin la voz de Qwen).

---

## 5. Crear el Space de la app

### 5.1 Preparar la carpeta

```powershell
powershell -ExecutionPolicy Bypass -File deploy\preparar_space_app.ps1
```

Genera `build\hf_space_app` con 10 ficheros (código, `Dockerfile`, `start.sh`,
`requirements.txt`, `descargar_artefactos.py`, `README.md`, `.dockerignore`).

### 5.2 Crear el Space

<https://huggingface.co/new-space> otra vez:

- **Space name**: `echopulse-ai`
- **SDK**: **Docker** → *Blank*
- **Hardware**: **CPU basic (free)**
- **Visibility**: Public

### 5.3 Subir el contenido

```powershell
git clone https://huggingface.co/spaces/tu-usuario/echopulse-ai
cd echopulse-ai
# copia TODO el contenido de build\hf_space_app (incluido .dockerignore)
Copy-Item ..\build\hf_space_app\* . -Recurse -Force
Copy-Item ..\build\hf_space_app\.dockerignore . -Force
git add .
git commit -m "EchoPulse AI"
git push
```

### 5.4 Configurar las variables (antes o después del primer build)

Settings → **Variables and secrets**:

| Nombre | Tipo | Valor |
|---|---|---|
| `ECHOPULSE_ARTIFACTS` | Variable | `tu-usuario/echopulse-artifacts` |
| `LLM_BASE_URL` | Variable | `https://<tu-usuario>-echopulse-qwen.hf.space/v1` |
| `LLM_MODEL` | Variable | `qwen` |
| `LLM_ORDER` | Variable | *(opcional)* `custom,groq,dashscope,hf,ollama` |
| `GROQ_API_KEY` | **Secret** | *(opcional)* alternativa rápida a Qwen local |

> Si el repo de artefactos es privado, agrega también `HF_TOKEN` como **Secret**.

### 5.5 Ver el build y arrancar

Pestaña **Logs**. Un build correcto termina con algo así (estas líneas están
copiadas de una ejecución real de la imagen en Docker):

```
🎧 EchoPulse AI — arranque en Hugging Face Spaces
   puerto: 7860
   artefactos: tu-usuario/echopulse-artifacts
   voz: endpoint compatible OpenAI → https://...-echopulse-qwen.hf.space/v1
==============================================================
✅ Artefactos presentes: no hay nada que descargar.
ℹ️ Sin HF_TOKEN válido: el router de Hugging Face no se usará (no hace falta).
✅ Cache de metadatos cargado: 38343 canciones
📊 Índice de fama cargado: 67,687 artistas | 95,539 claves (artista,título)
✅ Módulo 2 listo | Canciones: 5710 | Vocab: 9880 | con popularidad: 1209 | con fama de artista: 5395 | clásicos: 244
🔌 Cargando Módulo 3 (IntentTransformer - Re-ranking) en cpu...
✅ Módulo 3 listo | Clases: 38343 | Vocab: 10000
[INFO] Booting worker with pid: 8
```

Tiempos reales medidos en esta máquina (i5 de 2 núcleos):

| Etapa | Tiempo |
|---|---|
| Descarga de los 216 MB de artefactos (HF→HF) | 5-20 s |
| Carga de Módulos 2 y 3 | 20-40 s (en HF con disco local, menos) |
| Primera respuesta con el Space de Qwen dormido | 1-3 min (cold start) |
| Respuesta con todo caliente | 5-15 s (Qwen 1.5B) / < 1 s (determinista) |

> ⚠️ Si haces la prueba local con Docker y montas las carpetas de Windows
> (`-v C:\...`), la carga de modelos se vuelve **mucho** más lenta: el I/O de
> los bind mounts de Windows no tiene nada que ver con el disco del Space.


### 5.6 Probar la app

```powershell
curl https://<tu-usuario>-echopulse-ai.hf.space/api/health
curl -X POST https://<tu-usuario>-echopulse-ai.hf.space/api/llm/probar
```

Abre la URL en el navegador: escribe «me siento triste y aburrido» y deberías
ver la respuesta, las canciones con enlaces a Spotify/YouTube y el badge
`VOZ :: …` debajo del mensaje.

---

## 6. Elegir la voz: 3 opciones (puedes cambiar sin rebuild)

| Opción | Qué configurar | Velocidad | Coste |
|---|---|---|---|
| **A. Qwen propio** (Space 1) | `LLM_BASE_URL` + `LLM_MODEL=qwen` | 5-15 s/respuesta en CPU | 0 |
| **B. Groq** (Qwen3-32B) | `GROQ_API_KEY` (secret) | < 2 s | 0 (cupo gratis) |
| **C. Sin voz** | nada | 0,3 s | 0, pero respuesta determinista |

Para usar **Groq** y que tenga prioridad sobre el Space de Qwen:

```
LLM_ORDER=groq,custom,ollama
```

Cambiar variables reinicia el contenedor (30-60 s) y **no** requiere build.

---

## 7. Verificación final (checklist)

> ✅ **Ya probado en local antes de escribir esta guía**: se construyó la misma
> imagen Docker, se levantó `llama-server` con Qwen y se llamó al agente de
> punta a punta. Resultados reales:
>
> - `/api/llm/probar` → `proveedor=custom`, `modelo=qwen`, `respuesta='listo'`.
> - `/api/chat` «me siento triste y aburrido» → `voz=custom`, canción real
>   citada, pregunta de cierre, sin repetir canciones.
> - `fame_index.parquet` cargó 67.687 artistas (con `pyarrow` correcto).
> - El Space de Qwen respondió `200` en 5,5 s con `llama-server` + GGUF.

- [ ] `GET /api/health` → `status: ok` y `modules.module2_retrieval: loaded`.
- [ ] `POST /api/llm/probar` → `ok: true`, `proveedor: custom` (Space Qwen) o `groq`.
- [ ] Chat: «quiero algo de rock pesado» devuelve canciones con enlaces.
- [ ] Segundo mensaje «ahora algo fiestero» **no repite** canciones del primero.
- [ ] La consola del Space muestra `🎯 Keywords (EN): …` en cada turno.
- [ ] `VOZ ::` bajo la respuesta indica el motor que respondió.

Latencias de referencia (CPU basic de 2 vCPU):

| Escenario | Turno completo |
|---|---|
| Solo determinista | < 1 s |
| Qwen 1.5B en el Space | 15-30 s |
| Groq | 3-6 s |

---

## 8. Actualizar el despliegue

- **Cambiar código**: edita en tu PC → `preparar_space_app.ps1` → copia al
  clon del Space → `git add . && git commit -m "..." && git push`. HF
  reconstruye solo.
- **Cambiar configuración**: Settings → Variables → guardar. Reinicio sin build.
- **Reiniciar de cero**: Settings → **Factory reboot**.
- **Ver logs en vivo**: pestaña Logs → *Container*.

---

## 9. Problemas comunes

| Síntoma | Causa probable | Solución |
|---|---|---|
| Build falla en `pip install` | versión sin wheel para Linux | revisa el log; ajusta `requirements.txt` |
| `Faltan artefacto(s)` y no descarga | repo mal escrito o privado | revisa `ECHOPULSE_ARTIFACTS`; si es privado, `HF_TOKEN` secret |
| Arranca pero el chat dice «problema técnico» | modelos no cargaron | busca el traceback en Logs → Container |
| `/api/llm/probar` devuelve 503 | Qwen Space dormido o URL mal | abre la URL del Space de Qwen y reintenta |
| Respuestas en «MODO DETERMINISTA» | sin LLM disponible | configura `LLM_BASE_URL` o `GROQ_API_KEY` |
| El Space se duerme | plan gratis | visítalo antes de la demo; o pasa a PRO |
| `503 Service Unavailable` al abrir | contenedor arrancando | espera 1-2 min y recarga |
| La primera respuesta tarda 2 min | cold start + descarga del GGUF | normal; despierta el Space antes |
| `⚠️ No se pudo cargar fame_index.parquet (Repetition level histogram size mismatch)` | `pyarrow` del contenedor más viejo que el que generó el parquet | usa `pyarrow==25.0.1` (ya está fijado); o regenera el índice |
| Build local de Docker ocupa mucho disco | imagen ~2 GB + caché | `docker builder prune -af`; borra imágenes de prueba |

Para leer un error de verdad: pestaña **Logs** → **Container**, busca la línea
`Traceback` o `ERROR`. La app imprime cada fase (`Fase 1…`, `Fase 2…`), así que
se ve exactamente dónde falló.

---

## 10. Costos y límites (plan gratis)

- CPU basic: 2 vCPU, 16 GB RAM, 50 GB disco, **gratis**.
- Los Spaces públicos gratuitos **se duermen** tras un periodo de inactividad.
- Los builds son públicos y tienen cola.
- Persistencia: el disco del contenedor es efímero (por eso los pesos se bajan
  en cada arranque). No guardes nada importante dentro del Space.
- El repo de artefactos y los Spaces públicos no tienen coste.

---

## Anexo A — Comandos de referencia rápida

```powershell
# 1) autenticarse
hf auth login
hf auth whoami

# 2) artefactos
python deploy\subir_artefactos.py --dry-run
python deploy\subir_artefactos.py --repo tu-usuario/echopulse-artifacts

# 3) carpeta del Space de la app
powershell -ExecutionPolicy Bypass -File deploy\preparar_space_app.ps1

# 4) publicar
cd build\hf_space_app   # o el clon del Space
git add . ; git commit -m "deploy" ; git push

# 5) probar en local la misma imagen antes de subir (opcional)
docker build -t echopulse-app:test build\hf_space_app
docker run --rm -p 7860:7860 `
  -v ${PWD}\echopulse_llm_orquestator\models:/app/models:ro `
  -v ${PWD}\tabla_maestra:/app/tabla_maestra:ro `
  -e ECHOPULSE_ARTIFACTS= -e OLLAMA_ENABLED=0 echopulse-app:test
```

## Anexo B — Estructura de los repos

**Repo de artefactos** (`tu-usuario/echopulse-artifacts`):

```
README.md
models/
  song_metadata.json
  fame_index.parquet
  tabla_maestra/{mst_mr_final.pth, embeddings.pt}
  talkplay/{vocab.json, song_map.pkl, intent_model.pth}
tabla_maestra/train/part-….parquet
```

**Space de la app** (`tu-usuario/echopulse-ai`):

```
Dockerfile  start.sh  requirements.txt  descargar_artefactos.py
README.md   .dockerignore
app.py  llm_client.py  conversacion.py
templates/index.html
```

**Space de Qwen** (`tu-usuario/echopulse-qwen`):

```
Dockerfile  README.md
```
