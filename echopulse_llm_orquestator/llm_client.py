# llm_client.py - Capa LLM de EchoPulse (Qwen gratis)
"""
Por qué existe este módulo
--------------------------
El router de Hugging Face (router.huggingface.co) ya NO sirve Qwen gratis: si la
cuenta no tiene créditos responde

    402 {"error": "You have no remaining credits. Purchase pre-paid credits..."}

con lo que el agente se quedaba sin voz y caía a respuestas enlatadas. Además,
el código anterior reintentaba 3 veces cada 402 (~8 s perdidos por turno).

Este cliente desacopla la app del proveedor: habla el protocolo OpenAI
(/chat/completions con `messages`) y prueba, en orden, todos los backends
configurados. Un proveedor que responde 401/402/404 se marca "caído" y se salta
durante horas, así el 402 de HF no vuelve a costar tiempo.

Backends soportados (todos con Qwen)
------------------------------------
1. LLM_BASE_URL   -> cualquier endpoint compatible OpenAI.
                     Ej.: un Hugging Face Space propio con Qwen, vLLM, LM Studio,
                     Groq (https://api.groq.com/openai/v1) o Alibaba DashScope.
2. Ollama local   -> Qwen desde un GGUF de Hugging Face. Gratis y offline.
3. Router de HF   -> solo si la cuenta tiene créditos (se detecta y se salta).

Variables de entorno (todas opcionales salvo que quieras usar ese backend):

    LLM_ORDER        orden de preferencia, p.ej. "custom,groq,dashscope,hf,ollama"
    LLM_BASE_URL     endpoint compatible OpenAI (sin /chat/completions)
    LLM_API_KEY      key de ese endpoint (puede ir vacía en local)
    LLM_MODEL        nombre del modelo en ese endpoint

    OLLAMA_BASE_URL  por defecto http://127.0.0.1:11434/v1
    OLLAMA_HOST      alternativa: http://127.0.0.1:11434
    OLLAMA_MODEL     por defecto se autodetecta el primer qwen instalado
    OLLAMA_KEEP_ALIVE minutos que el modelo sigue en RAM (por defecto "30m")

    HF_TOKEN / HF_MODEL_ID   router de Hugging Face (requiere créditos)
    GROQ_API_KEY / GROQ_MODEL
    DASHSCOPE_API_KEY / DASHSCOPE_MODEL   (Qwen nativo de Alibaba)
    OPENROUTER_API_KEY / OPENROUTER_MODEL
"""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

import requests

# ---------------------------------------------------------------------------
# Limpieza de la salida del modelo
# ---------------------------------------------------------------------------
# Qwen3 puede razonar en voz alta con  thinking...<｜end▁of▁thinking｜>; eso no debe llegar
# al usuario. También se quitan tokens especiales y prefijos tipo "EchoPulse:".
_RE_THINK = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.DOTALL | re.IGNORECASE)
_RE_THINK_SUELTO = re.compile(r"</?think(?:ing)?>", re.IGNORECASE)
_RE_TOKEN_ESPECIAL = re.compile(r"<\|[^>]{1,40}\|>")
_RE_ESPACIOS = re.compile(r"\s+")

PREFIJO_ASSISTANT = re.compile(r"^\s*(?:echopulse|asistente|assistant|respuesta)\s*:\s*", re.I)


def limpiar_salida(texto: str) -> str:
    """Normaliza la respuesta del modelo para mostrarla en el chat."""
    if not texto:
        return ""
    texto = _RE_THINK.sub("", texto)
    texto = _RE_THINK_SUELTO.sub("", texto)
    texto = _RE_TOKEN_ESPECIAL.sub("", texto)
    texto = PREFIJO_ASSISTANT.sub("", texto)
    texto = texto.replace("**", "").replace("##", "")
    return _RE_ESPACIOS.sub(" ", texto).strip()


# ---------------------------------------------------------------------------
# Estructuras
# ---------------------------------------------------------------------------
@dataclass
class Proveedor:
    nombre: str
    base_url: str
    modelo: str
    api_key: str = ""
    local: bool = False
    timeout: int = 60
    # En algunos backends (Ollama) conviene mantener el modelo caliente.
    keep_alive: str = ""

    @property
    def url_chat(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    @property
    def url_modelos(self) -> str:
        return self.base_url.rstrip("/") + "/models"


@dataclass
class RespuestaLLM:
    texto: str
    proveedor: str
    modelo: str
    latencia_ms: float

    def __str__(self) -> str:  # pragma: no cover - ayuda al depurar
        return self.texto


@dataclass
class _Caido:
    hasta: float
    motivo: str


# ---------------------------------------------------------------------------
# Helpers de configuración
# ---------------------------------------------------------------------------
def _env(*nombres: str, default: str = "") -> str:
    for nombre in nombres:
        valor = os.getenv(nombre)
        if valor and valor.strip():
            return valor.strip()
    return default


def _host_ollama() -> str:
    host = _env("OLLAMA_BASE_URL")
    if host:
        return host.rstrip("/")
    host = _env("OLLAMA_HOST", default="http://127.0.0.1:11434").rstrip("/")
    if not host.endswith("/v1"):
        host += "/v1"
    return host


def construir_proveedores() -> list[Proveedor]:
    """Arma la lista de backends a partir del entorno (sin red)."""
    proveedores: list[Proveedor] = []

    base = _env("LLM_BASE_URL")
    if base:
        proveedores.append(
            Proveedor(
                nombre="custom",
                base_url=base,
                api_key=_env("LLM_API_KEY"),
                modelo=_env("LLM_MODEL", default="qwen"),
                timeout=int(_env("LLM_TIMEOUT", default="90")),
            )
        )

    if _env("GROQ_API_KEY"):
        proveedores.append(
            Proveedor(
                nombre="groq",
                base_url=_env("GROQ_BASE_URL", default="https://api.groq.com/openai/v1"),
                api_key=_env("GROQ_API_KEY"),
                modelo=_env("GROQ_MODEL", default="qwen/qwen3-32b"),
            )
        )

    if _env("DASHSCOPE_API_KEY"):
        proveedores.append(
            Proveedor(
                nombre="dashscope",
                base_url=_env(
                    "DASHSCOPE_BASE_URL",
                    default="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                ),
                api_key=_env("DASHSCOPE_API_KEY"),
                modelo=_env("DASHSCOPE_MODEL", default="qwen-plus"),
            )
        )

    if _env("OPENROUTER_API_KEY"):
        proveedores.append(
            Proveedor(
                nombre="openrouter",
                base_url=_env("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1"),
                api_key=_env("OPENROUTER_API_KEY"),
                modelo=_env("OPENROUTER_MODEL", default="qwen/qwen3-4b:free"),
            )
        )

    if _env("HF_TOKEN"):
        proveedores.append(
            Proveedor(
                nombre="hf",
                base_url=_env("HF_BASE_URL", default="https://router.huggingface.co/v1"),
                api_key=_env("HF_TOKEN"),
                modelo=_env("HF_MODEL_ID", default="Qwen/Qwen3-4B-Instruct-2507"),
            )
        )

    if _env("OLLAMA_ENABLED", default="1") not in ("0", "false", "False"):
        proveedores.append(
            Proveedor(
                nombre="ollama",
                base_url=_host_ollama(),
                modelo=_env("OLLAMA_MODEL", default=""),
                local=True,
                timeout=int(_env("OLLAMA_TIMEOUT", default="240")),
                keep_alive=_env("OLLAMA_KEEP_ALIVE", default="30m"),
            )
        )

    orden = [p.strip().lower() for p in _env("LLM_ORDER", default="").split(",") if p.strip()]
    if orden:
        posicion = {nombre: i for i, nombre in enumerate(orden)}
        # Los que no aparecen en LLM_ORDER quedan al final, conservando su orden.
        proveedores.sort(key=lambda p: posicion.get(p.nombre, len(orden)))
    else:
        # Orden por defecto: endpoints explícitos y nubes gratis primero,
        # HF (puede estar sin créditos) al final y Ollama como red de seguridad.
        predeterminado = ["custom", "groq", "dashscope", "openrouter", "hf", "ollama"]
        proveedores.sort(key=lambda p: predeterminado.index(p.nombre))
    return proveedores


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------
class ClienteLLM:
    """Cliente chat multi-proveedor, con memoria de proveedores caídos."""

    # Cuánto se salta un proveedor según el tipo de fallo (segundos)
    COOLDOWN_DURO = 6 * 60 * 60   # 401/402/403/404/422: credenciales o modelo
    COOLDOWN_RAPIDO = 10 * 60     # 400: petición inválida para ese backend
    COOLDOWN_SUAVE = 60           # 429/5xx/red: puede recuperarse

    def __init__(
        self,
        proveedores: Iterable[Proveedor] | None = None,
        log: Callable[[str], None] = print,
    ):
        self.proveedores = list(proveedores) if proveedores is not None else construir_proveedores()
        self.log = log
        self._caidos: dict[str, _Caido] = {}
        self._modelos: dict[str, str] = {}
        self._lock = threading.Lock()
        self._sesion = requests.Session()
        self._ultimo_ok: RespuestaLLM | None = None
        self._ultimo_error: dict[str, str] = {}
        self._hilo_precalentado: threading.Thread | None = None

    # -- estado -------------------------------------------------------------
    @property
    def activo(self) -> bool:
        """¿Hay algún backend con modelo resoluble en este momento?"""
        return any(
            not self._esta_caido(p.nombre) and self._resolver_modelo(p)
            for p in self.proveedores
        )

    def _esta_caido(self, nombre: str) -> bool:
        with self._lock:
            caido = self._caidos.get(nombre)
            if caido and caido.hasta > time.time():
                return True
            if caido:
                # El castigo expiró: se le da otra oportunidad.
                del self._caidos[nombre]
                return False
            return False

    def _marcar_caido(self, nombre: str, motivo: str, segundos: int) -> None:
        with self._lock:
            self._caidos[nombre] = _Caido(hasta=time.time() + segundos, motivo=motivo)
            self._ultimo_error[nombre] = motivo

    def revivir(self, nombre: str | None = None) -> None:
        """Permite reintentar un proveedor a mano (útil tras recargar créditos)."""
        with self._lock:
            if nombre:
                self._caidos.pop(nombre, None)
            else:
                self._caidos.clear()

    def estado(self) -> dict:
        with self._lock:
            ahora = time.time()
            caidos = {
                nombre: {"motivo": c.motivo, "queda_s": int(c.hasta - ahora)}
                for nombre, c in self._caidos.items()
                if c.hasta > ahora
            }
            ultimo = None
            if self._ultimo_ok:
                ultimo = {
                    "proveedor": self._ultimo_ok.proveedor,
                    "modelo": self._ultimo_ok.modelo,
                    "latencia_ms": round(self._ultimo_ok.latencia_ms, 1),
                }
        return {
            "orden": [p.nombre for p in self.proveedores],
            "disponibles": [p.nombre for p in self.proveedores if not self._esta_caido(p.nombre)],
            "caidos": caidos,
            "ultimo_ok": ultimo,
            "modelos": dict(self._modelos),
        }

    def descripcion(self) -> str:
        """Etiqueta corta para la UI: qué backend con modelo está sirviendo."""
        ultimo = self._ultimo_ok
        if ultimo:
            return f"{ultimo.proveedor.upper()} · {ultimo.modelo}"
        for proveedor in self.proveedores:
            if self._esta_caido(proveedor.nombre):
                continue
            modelo = self._resolver_modelo(proveedor)
            if modelo:
                return f"{proveedor.nombre.upper()} · {modelo}"
        return "SIN_LLM"

    # -- descubrimiento de modelo ------------------------------------------
    def _resolver_modelo(self, proveedor: Proveedor) -> str:
        if proveedor.modelo:
            return proveedor.modelo
        if proveedor.nombre in self._modelos:
            return self._modelos[proveedor.nombre]

        modelo = ""
        if proveedor.nombre == "ollama":
            modelo = self._mejor_modelo_ollama(proveedor)
        elif proveedor.nombre == "openrouter":
            modelo = self._buscar_modelo_gratis(proveedor, "qwen")

        if not modelo:
            modelo = "qwen2.5:3b-instruct" if proveedor.nombre == "ollama" else "qwen"
        self._modelos[proveedor.nombre] = modelo
        return modelo

    def _mejor_modelo_ollama(self, proveedor: Proveedor) -> str:
        try:
            respuesta = self._sesion.get(
                proveedor.base_url.replace("/v1", "") + "/api/tags", timeout=5
            )
            respuesta.raise_for_status()
            modelos = [m.get("name", "") for m in respuesta.json().get("models", [])]
        except Exception:
            return ""
        if not modelos:
            return ""

        # Preferir Qwen instruct y, entre ellos, el más grande hasta 4B (mejor
        # conversación sin volverse inusable en CPU). OLLAMA_MODEL manda si está.
        def puntaje(nombre: str) -> tuple:
            n = nombre.lower()
            tamano = re.search(r"(\d+(?:\.\d+)?)b", n)
            billones = float(tamano.group(1)) if tamano else 0.0
            return (
                "qwen" in n,
                "instruct" in n,
                "coder" not in n and "thinking" not in n,
                min(billones, 4.0),
            )

        return sorted(modelos, key=puntaje, reverse=True)[0]

    def _buscar_modelo_gratis(self, proveedor: Proveedor, familia: str) -> str:
        if not proveedor.api_key:
            return ""
        try:
            respuesta = self._sesion.get(
                proveedor.url_modelos,
                headers={"Authorization": f"Bearer {proveedor.api_key}"},
                timeout=15,
            )
            respuesta.raise_for_status()
            datos = respuesta.json().get("data", [])
        except Exception:
            return ""
        candidatos = []
        for modelo in datos:
            ident = modelo.get("id", "")
            if familia not in ident.lower():
                continue
            precios = modelo.get("pricing") or {}
            gratis = str(precios.get("prompt", "1")) in ("0", "0.0")
            candidatos.append((gratis, ":free" in ident, ident))
        if not candidatos:
            return ""
        candidatos.sort(reverse=True)
        return candidatos[0][2]

    # -- llamada principal --------------------------------------------------
    def chat(
        self,
        messages: Sequence[dict],
        *,
        max_tokens: int = 220,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Sequence[str] | None = None,
        proposito: str = "chat",
        solo_proveedor: str | None = None,
    ) -> RespuestaLLM | None:
        """Prueba los proveedores en orden y devuelve la primera respuesta válida."""
        orden = self.proveedores
        if solo_proveedor:
            orden = [p for p in orden if p.nombre == solo_proveedor]

        for proveedor in orden:
            if self._esta_caido(proveedor.nombre):
                continue
            modelo = self._resolver_modelo(proveedor)
            if not modelo:
                continue

            payload: dict = {
                "model": modelo,
                "messages": list(messages),
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "stream": False,
            }
            if stop:
                payload["stop"] = list(stop)
            if proveedor.keep_alive:
                # Ollama lo acepta; los routers OpenAI suelen ignorarlo.
                payload["keep_alive"] = proveedor.keep_alive

            cabeceras = {"Content-Type": "application/json"}
            if proveedor.api_key:
                cabeceras["Authorization"] = f"Bearer {proveedor.api_key}"

            inicio = time.time()
            try:
                respuesta = self._sesion.post(
                    proveedor.url_chat,
                    headers=cabeceras,
                    json=payload,
                    timeout=proveedor.timeout,
                )
            except requests.exceptions.Timeout:
                self._marcar_caido(proveedor.nombre, "timeout", self.COOLDOWN_SUAVE)
                self.log(f"⏱️  {proveedor.nombre}: timeout ({proveedor.timeout}s) en «{proposito}»")
                continue
            except requests.exceptions.ConnectionError as exc:
                # Ollama apagado o endpoint inalcanzable: no es un error fatal.
                self._marcar_caido(proveedor.nombre, "sin conexión", self.COOLDOWN_SUAVE)
                self.log(f"🔌 {proveedor.nombre}: sin conexión ({_resumen_error(exc)})")
                continue
            except Exception as exc:  # pragma: no cover - defensivo
                self._marcar_caido(proveedor.nombre, str(exc)[:120], self.COOLDOWN_SUAVE)
                self.log(f"❌ {proveedor.nombre}: {_resumen_error(exc)}")
                continue

            estado = respuesta.status_code
            if estado == 200:
                try:
                    datos = respuesta.json()
                    texto = datos["choices"][0]["message"]["content"]
                except Exception:
                    self._marcar_caido(proveedor.nombre, "respuesta JSON inválida", self.COOLDOWN_SUAVE)
                    self.log(f"❌ {proveedor.nombre}: respuesta inesperada {respuesta.text[:160]}")
                    continue

                texto = limpiar_salida(texto)
                if not texto:
                    self.log(f"⚠️ {proveedor.nombre}: respuesta vacía")
                    continue

                completado = RespuestaLLM(
                    texto=texto,
                    proveedor=proveedor.nombre,
                    modelo=modelo,
                    latencia_ms=(time.time() - inicio) * 1000,
                )
                with self._lock:
                    self._ultimo_ok = completado
                return completado

            detalle = _detalle_error(respuesta)

            if estado in (401, 402, 403, 404):
                # Credenciales, créditos o modelo inexistente: reintentar no sirve.
                self._marcar_caido(proveedor.nombre, f"HTTP {estado}: {detalle}", self.COOLDOWN_DURO)
                self.log(f"🚫 {proveedor.nombre} deshabilitado ({estado}): {detalle}")
                continue

            if estado in (400, 422):
                self._marcar_caido(proveedor.nombre, f"HTTP {estado}: {detalle}", self.COOLDOWN_RAPIDO)
                self.log(f"❌ {proveedor.nombre}: petición rechazada ({estado}): {detalle}")
                continue

            if estado == 429 or estado >= 500:
                espera = _retry_after(respuesta)
                # Reintentar solo si la espera es corta (o no la indican).
                if espera is None or espera <= 5:
                    if espera:
                        time.sleep(espera)
                    reintento = self._reintentar(proveedor, cabeceras, payload)
                    if reintento is not None:
                        with self._lock:
                            self._ultimo_ok = reintento
                        return reintento
                self._marcar_caido(proveedor.nombre, f"HTTP {estado}: {detalle}", self.COOLDOWN_SUAVE)
                self.log(f"⏳ {proveedor.nombre} saturado ({estado}): {detalle}")
                continue

            self.log(f"❌ {proveedor.nombre}: HTTP {estado} {detalle}")
            continue

        return None

    def _reintentar(
        self, proveedor: Proveedor, cabeceras: dict, payload: dict
    ) -> RespuestaLLM | None:
        """Un único reintento tras 429/5xx con Retry-After corto."""
        inicio = time.time()
        try:
            respuesta = self._sesion.post(
                proveedor.url_chat,
                headers=cabeceras,
                json=payload,
                timeout=proveedor.timeout,
            )
            if respuesta.status_code != 200:
                return None
            datos = respuesta.json()
            texto = limpiar_salida(datos["choices"][0]["message"]["content"])
        except Exception:
            return None
        if not texto:
            return None
        return RespuestaLLM(
            texto=texto,
            proveedor=proveedor.nombre,
            modelo=self._resolver_modelo(proveedor),
            latencia_ms=(time.time() - inicio) * 1000,
        )

    # -- diagnóstico y calentamiento ---------------------------------------
    def diagnosticar(self, hilo: bool = True) -> threading.Thread | None:
        """Ping de 1 token por proveedor, en segundo plano.

        Sirve para dos cosas: deja Qwen cargado en RAM (primer turno rápido) y
        descubre al arrancar que el router de HF ya no tiene créditos, para que
        `/api/health` diga la verdad desde el primer segundo en vez de esperar
        al primer mensaje del usuario.
        """
        if self._hilo_precalentado is not None:
            return self._hilo_precalentado

        def _tarea() -> None:
            for proveedor in list(self.proveedores):
                if self._esta_caido(proveedor.nombre):
                    continue
                modelo = self._resolver_modelo(proveedor)
                if not modelo:
                    self.log(f"ℹ️ {proveedor.nombre}: sin modelo disponible, se omite")
                    continue
                inicio = time.time()
                salida = self.chat(
                    [{"role": "user", "content": "ping"}],
                    max_tokens=1,
                    temperature=0.0,
                    proposito="diagnostico",
                    solo_proveedor=proveedor.nombre,
                )
                if salida:
                    self.log(
                        f"🔥 {proveedor.nombre} listo ({modelo}) en {time.time() - inicio:.1f}s"
                    )

        if not hilo:
            _tarea()
            return None
        self._hilo_precalentado = threading.Thread(target=_tarea, name="diagnostico-llm", daemon=True)
        self._hilo_precalentado.start()
        return self._hilo_precalentado

    # Alias histórico
    precalentar = diagnosticar


# ---------------------------------------------------------------------------
# Utilidades HTTP
# ---------------------------------------------------------------------------
def _detalle_error(respuesta: requests.Response) -> str:
    """Saca el mensaje útil del cuerpo de error (HF pone el motivo en 'error')."""
    try:
        datos = respuesta.json()
        if isinstance(datos, dict):
            error = datos.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error)[:200]
            if error:
                return str(error)[:200]
            if datos.get("message"):
                return str(datos["message"])[:200]
    except Exception:
        pass
    return (respuesta.text or "").strip()[:200] or "sin detalle"


def _resumen_error(exc: BaseException) -> str:
    texto = str(exc)
    if len(texto) > 160:
        texto = texto[:160] + "…"
    return f"{type(exc).__name__}: {texto}"


def _retry_after(respuesta: requests.Response) -> float | None:
    valor = respuesta.headers.get("Retry-After")
    if not valor:
        return None
    try:
        return float(valor)
    except ValueError:
        return None
