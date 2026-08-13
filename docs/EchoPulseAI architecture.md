# Arquitectura Detallada de EchoPulse AI: Triple-Encoder por Intención Conversacional (Encoder-Decoder)

Esta arquitectura implementa un modelo de recomendación basado en la **Afinidad de Contenido-a-Conversación**, utilizando **tres Transformadores en modo Encoder-Decoder** especializados y el marco RAG (Retrieval-Augmented Generation) orquestado por un Large Language Model (LLM).

El uso del modo Encoder-Decoder para cada Transformer (Seq2Seq) se justifica como un mecanismo de **pre-entrenamiento auto-supervisado**. Las tareas de Decodificación fuerzan a cada Encoder a generar representaciones vectoriales ($E$) más ricas y contextualizadas para la posterior tarea de _ranking_ y recuperación.

## MÓDULO A: ENCODERS UNIMODALES ESPECIALIZADOS (Proceso Offline)

Objetivo: Generar representaciones vectoriales densas y de alta calidad ($E_{Song}$) para cada canción, fusionando contenido temático, afectivo y técnico. El vector final se extrae siempre del **bloque Encoder**. La separación en tres Encoders es crítica para modelar correctamente las diferentes **modalidades de datos** (Texto Secuencial vs. Tabular Relacional vs. Diálogo Secuencial).

Componente

Datasets de Entrada

Variables Utilizadas

Función de Atención Multi-Cabeza y Tarea del Decoder (Énfasis en la Modalidad de Atención)

**1. Lyrical-Afective Encoder-Decoder**

`Lyrics 1950-2019` + `WASABI Songs`

**Texto y Estructura:** `lyrics`, `abstract`, `len` (Lyrics 1950-2019), `title`, `artist`, `writer`. **Afectivas/Tópicos (Claves para la búsqueda):** `valence`, `arousal`, `valence_predicted`, `arousal_predicted` (WASABI); `sadness`, `feelings`, `romantic`, `dating`, `violence`, `obscene`, `music`, `world/life`, `communication`, `shake the audience`, `family/gospel`, `movement/places`, `light/visual perceptions`, `family/spiritual`, `like/girls`, `topic`.

**Modalidad de Atención: Secuencial/Lingüística.** Las cabezas se entrenan para ponderar la **conexión entre el texto y la intensidad emocional/temática** (`valence`/`sadness`). **Decoder (Tarea Auxiliar):** Generación de un **resumen conciso (`abstract`)** o **predicción de las variables binarias de Tópicos** a partir del texto. Esto asegura la compresión semántica y emocional en $E_{Lyrical}$.

**2. Tabular-Metadata Encoder-Decoder**

`Million Song Dataset` (MSD) + Variables restantes

**Técnicas/Acústicas (MSD/Lyrics):** `danceability`, `energy`, `key`, `loudness`, `mode`, `speechiness`, `acousticness`, `instrumentalness`, `liveness`, `tempo`, `duration_ms`, `time_signature`. **Contextuales/Temporales:** `year`, `release_date`, `age`, `genre`, `popularity`, `album_genre`, `rank`, `bpm`. **Identificadores/Otros:** `track_id`, `artist_name`, `recordLabel`, `producer`, `id_song_deezer`, `isrc`, `isClassic`.

**Modalidad de Atención: Relacional/Tabular.** Las cabezas analizan **todas las dependencias cruzadas** entre atributos numéricos y categóricos. El modelo actúa como un _TabTransformer_, forzado a entender la coherencia interna de las _features_ no textuales. **Decoder (Tarea Auxiliar):** Se entrena para **predecir variables categóricas** (e.g., `genre`, `key`) o **reconstruir un subconjunto de variables numéricas** a partir del resto de los atributos, forzando la coherencia del vector $E_{Metadata}$.

**3. Conversational Intent Encoder-Decoder (TalkPlay2)**

`TalkPlay2`

**Texto y Objetivos:** `content_text`, `goal_description`. **Contexto de Sesión:** `session_id`, `turn_number`, `speaker_role`, `global_turn_id`, `is_recommendation_target`. **Demográficos:** `user_gender`, `user_music_culture`.

**Modalidad de Atención: Diálogo Secuencial.** El Encoder **concatenará la `goal_description`** con la **historia secuencial de `content_text`** (multi-turno). Las cabezas de atención se entrenan para **mantener la meta de la sesión** e **identificar el** _**shift**_ **de intención** en el último turno del usuario. **Decoder (Tarea Auxiliar):** Se entrena para generar la **siguiente acción conversacional/recomendación** (el `track_id` del rol `music`) y el _**slot-filling**_ **estructurado en JSON**, asegurando que el vector $E_{Intent}$ capture la intención **secuencial** del diálogo.

### Detalles Técnicos y de Preprocesamiento de Embeddings

#### 1. Mapeo Maestro e Indexación para la Coherencia de Features ($E_{Song}$)

El problema de bases de datos separadas que referencian canciones distintas para el mismo ID/título es crítico. Por lo tanto, la unificación no es un simple `JOIN`, sino un proceso de **Mapeo Maestro e Indexación de Alta Confianza** para construir una "Tabla Maestra de Canciones" única, donde cada fila (`track_id` maestro) contiene todos los _features_ correctos (letras y metadata). **Este es un paso MANDATORIO antes de cualquier entrenamiento.**

- **Fuentes a Integrar:** `Lyrics 1950-2019`, `WASABI Songs`, y `Million Song Dataset` (MSD).
- **Estrategia de Alineación (Prioridad Descendente):**

  1.  **Alineación Fuerte (ID):** Se utiliza cualquier ID de estándar de la industria presente en ambos sets (e.g., `id_song_deezer`, `id_song_musicbrainz`, `isrc`) como clave primaria para el `JOIN` (indexación por identificador único).
  2.  **Alineación Media (Texto Normalizado):** Para las canciones que no tienen IDs en común, se realiza un `INNER JOIN` utilizando las claves `artist` y `title` después de una **normalización estricta** (minúsculas, eliminación de puntuación, lematización de palabras comunes como "The").
  3.  **Alineación Débil (Fuzzy Matching):** Se utiliza una distancia de edición (ej., Levenshtein) o _fuzzy matching_ para canciones con ligeras discrepancias en el título. Solo se aceptan coincidencias con un umbral de confianza muy alto (ej., >95%) para minimizar la contaminación de datos.

- **Resultado y Proceso de Encoder:** Solo las canciones que pasen esta alineación de alta confianza formarán parte del corpus de entrenamiento. Para cada **instancia de canción maestra** se alimentarán al mismo tiempo:

  - **Features Lyrical/Afectivas** al **Lyrical-Afective Encoder**.
  - **Features Tabular/Metadata** al **Tabular-Metadata Encoder**.
  - Esto garantiza que los dos vectores de salida ($E_{Lyrical}$ y $E_{Metadata}$) que se fusionan para crear $E_{Song}$ pertenezcan _siempre_ al mismo objeto real (la misma canción).

#### 2. Definición de Hiperparámetros del Transformer

Para asegurar la capacidad de modelado profundo y la consistencia dimensional en los tres Transformadores Encoder-Decoder, se definen los siguientes hiperparámetros estándar, siguiendo las prácticas de modelos de lenguaje modernos (ej. BERT-Base):

Hiperparámetro

Notación

Valor Definido

Descripción

**Dimensión del Modelo/Embedding**

$d_{\text{model}}$

$\mathbf{768}$

Dimensión de salida de cada capa de atención y de los _embeddings_ de canción ($E_{Song}$, $E_{Lyrical}$, $E_{Metadata}$, $E_{Intent}$).

**Dimensión de Feed-Forward**

$d_{\text{ff}}$

$\mathbf{3072}$

Dimensión interna de la capa _Feed-Forward_ del Transformer ($4 \times d_{\text{model}}$).

**Número de Cabezas de Atención**

$H$

$\mathbf{12}$

Número de proyecciones paralelas en el mecanismo Multi-Cabeza.

**Dimensión de Key y Value**

$d_{k} = d_{v}$

$\mathbf{64}$

Dimensión de las proyecciones de Query, Key y Value ($d_{\text{model}} / H$).

### Fusión de Embeddings de Canción y Database

- **Fusión Vectorial:** Los vectores $E_{Lyrical}$ y $E_{Metadata}$ (ambos extraídos de los respectivos **Encoders**) se concatenan y se proyectan linealmente a través de una capa **Feed-Forward**.

  $$E_{Song} = \text{FeedForward}(\text{Concatenate}(E_{Lyrical}, E_{Metadata}))$$

  _Resultado:_ $E_{Song}$ es el vector de contenido final **multimodal** para cada canción.

- **Indexación:** $E_{Song}$ se almacena en la **Vector Database** (e.g., Pinecone/FAISS) para la búsqueda semántica de afinidad.

## MÓDULO B: ORQUESTACIÓN Y RECUPERACIÓN RAG (Híbrida)

### 1. Codificación de Intención y Búsqueda

- **Codificación de Intención:** El **Conversational Intent Encoder-Decoder** procesa la consulta del usuario y el vector $E_{Intent}$ es extraído del **Encoder**.
- **Agente Orquestador (LLM):** Gestiona la búsqueda híbrida utilizando el $E_{Intent}$ como _Query_.

  - **Vector Search:** Usa $E_{Intent}$ para encontrar canciones afines en la Vector Database.
  - **Lexical Search:** Usa filtros clave extraídos del _slot-filling_ del Decoder para la búsqueda exacta en el **Keyword Index**.

- **Output:** $C_{k}$ **(Lista de Candidatos Iniciales)**.

## MÓDULO C: RANKING FINAL Y ENTREGA (Online)

### 1. Re-Ranking por Afinidad de Contenido-a-Intención

- **Arquitectura:** **Cross-Encoder Transformer** (Modelo de _Re-Ranking_).
- **Función:** El $E_{Intent}$ (como **Query**) interactúa con los $E_{Song}$ de los candidatos $C_{k}$ (como **Key** y **Value**) a través de la Atención Cruzada.
- **Optimización:** Uso de **Sparse Attention** para asegurar la eficiencia y un **Puntaje de Relevancia Final (**$R$**)** rápido y preciso.

### 2. Capa de Entrega (LLM Generativo)

- **Ranking:** Las Top-N canciones se seleccionan basándose en el puntaje $R$.
- **Generación de Respuesta:** El **LLM Orquestador** genera la respuesta conversacional que **justifica la recomendación**.

**Diagrama Simplificado del Flujo (Sin Historial de Usuario)**

$$\begin{array}{l} \text{Offline: } (\text{Letras, WASABI, MSD}) \xrightarrow{\text{Mapeo Maestro} \rightarrow \text{Encoder-Decoder Auxiliar}} E_{Song} \xrightarrow{\text{Indexación}} \text{Database} \\ \text{Online: } \text{Consulta} \xrightarrow{E_{Intent}} \text{RAG Híbrido} \rightarrow C_{k} \xrightarrow{\text{Cross-Encoder}} \text{Ranking} \xrightarrow{\text{LLM}} \text{Recomendación Final} \end{array}$$

# Diagrama de Arquitectura: EchoPulse AI - Recomendación Multimodal

Este diagrama visualiza el flujo de datos y la interacción de los cuatro modelos Transformer (tres Encoder-Decoder especializados y un Cross-Encoder para Re-Ranking) en el sistema de recomendación EchoPulse AI.

## MÓDULO A: GENERACIÓN Y FUSIÓN DE EMBEDDINGS (Offline)

El Módulo A se ejecuta fuera de línea para generar el vector de contenido denso de la canción ($E_{Song}$). Este proceso es la "Tabla Maestra de Features".

Paso

Descripción

Componentes Principales

**1. Mapeo Maestro (Alineación)**

Se asegura que las _features_ (Lírica, Metadata) pertenezcan a la **misma canción** antes de la codificación.

_Proceso ETL mandatorio_

**2. Codificación Lyrical-Afective (**$E_{Lyrical}$**)**

El Transformer modela la **secuencia de las letras** y la intensidad de las **variables emocionales/afectivas** (`valence`, `sadness`).

**Transformer 1** (Encoder-Decoder)

**3. Codificación Tabular-Metadata (**$E_{Metadata}$**)**

El Transformer (estilo _TabTransformer_) modela las **relaciones cruzadas** entre atributos técnicos (`BPM`, `energy`, `genre`) y temporales.

**Transformer 2** (Encoder-Decoder)

**4. Fusión Multimodal**

Se concatenan $E_{Lyrical}$ y $E_{Metadata}$ y se proyectan linealmente a la dimensión $d_{\text{model}}=768$.

$\mathbf{E_{Song}} = \text{FeedForward}(\text{Concatenate}(E_{Lyrical}, E_{Metadata}))$

**5. Indexación**

$E_{Song}$ se almacena en una base de datos vectorial para la recuperación en línea.

**Vector Database**

## MÓDULO B & C: FLUJO DE CONSULTA Y RANKING (Online)

El Módulo B y C se ejecutan en tiempo real cuando el usuario introduce una consulta.

Paso

Descripción

Componentes Principales

**6. Codificación de Intención (**$E_{Intent}$**)**

El Transformer procesa la **secuencia de diálogo** (`content_text`) y el **objetivo de la sesión** (`goal_description`) para generar el vector de intención.

**Transformer 3** (Encoder-Decoder)

**7. Recuperación Híbrida (RAG)**

El LLM Orquestador usa $E_{Intent}$ para: 1. **Búsqueda Vectorial** (afinidad semántica); 2. **Búsqueda Lexical** (filtros exactos extraídos del Decoder, ej., "genre=rock").

**Agente LLM Orquestador** + **Vector Database**

**8. Re-Ranking (Afinidad Final)**

Un **Cross-Encoder** compara directamente el vector de intención ($E_{Intent}$) contra los vectores de canción ($E_{Song}$) de los candidatos recuperados ($C_{k}$) para generar un puntaje de relevancia final ($R$).

**Cross-Encoder Transformer**

**9. Generación de Respuesta**

El LLM recibe las Top-N canciones y genera una respuesta conversacional, **justificando la recomendación**.

**LLM Generativo**

## ESTRUCTURA DE TRANSFORMERS Y SUS FUNCIONES

Transformer

Tipo de Tarea

Foco de Atención

**1. Lyrical-Afective**

Contenido (Texto/Emoción)

Dependencias Lingüísticas

**2. Tabular-Metadata**

Contenido (Datos Técnicos)

Relaciones Tabulares (Atributos entre sí)

**3. Conversational Intent**

Contexto (Diálogo Secuencial)

Sesión + Intención del Último Turno

**4. Cross-Encoder**

Ranking (Afinidad $Q-K$)

Atención Cruzada entre $E_{Intent}$ (Query) y $E_{Song}$ (Key)
