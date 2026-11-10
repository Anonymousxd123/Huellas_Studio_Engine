# Huellas Studio Engine

Motor de preparación y producción visual para episodios de **Huellas Studio**.

## Requisitos

- Python 3.10 o superior.
- ComfyUI activo y accesible por su API HTTP (por defecto `http://127.0.0.1:8188`).
- Los checkpoints y nodos personalizados requeridos por `workflows/image/character_generator_api.json`.
- Los archivos maestros de personajes en `~/Huellas_Studio_Assets/characters`.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev,background-removal]"
```

En Windows, activa el entorno con `.venv\\Scripts\\activate`.

### Instalar síntesis de voz local (macOS)

Kokoro es opcional: no se instala ni descarga el modelo hasta que decidas activar esta etapa. En macOS, ejecuta:

```bash
bash scripts/setup_tts_macos.sh
```

El instalador configura `espeak-ng` con Homebrew y añade el extra `tts` al entorno virtual existente. Los pesos de Kokoro y las voces se descargan automáticamente la primera vez que generes audio.

## Comprobación inicial

```bash
huellas check
python scripts/validate_bilingual.py --episode episode_001
python scripts/prepare_episode.py --episode episode_001
python scripts/preflight_production.py --episode episode_001
```

El preflight acepta `--skip-comfyui` para validar estructura, referencias, workflow y traducciones sin que ComfyUI esté encendido.

## Preparar recortes de personajes

```bash
python scripts/build_character_assets.py
```

Los recortes se guardan en `~/Huellas_Studio_Assets/characters/cutouts_v2`. El compositor necesita:

- `dog_master_rgba.png`
- `cat_master_rgba.png`

## Producción visual de un episodio

El siguiente comando ejecuta el paquete completo de previsualización bilingüe: genera los fondos que falten, compone las escenas, prepara manifiestos de voz y subtítulos, y renderiza los MP4 de revisión:

```bash
python scripts/produce_episode_preview.py --episode episode_001
```

Para reutilizar las escenas ya compuestas y regenerar solo manifiestos, subtítulos y MP4:

```bash
python scripts/produce_episode_preview.py --episode episode_001 --skip-visuals
```

Si prefieres ejecutar únicamente la etapa visual:

```bash
python scripts/run_episode_composite.py --episode episode_001
```

El proceso es reanudable: reutiliza los fondos existentes y continúa con las escenas pendientes. Para regenerar todos los fondos:

```bash
python scripts/run_episode_composite.py --episode episode_001 --force
```

Opciones frecuentes:

- `--url http://127.0.0.1:8188`: dirección de ComfyUI.
- `--seed 20261109`: semilla base reproducible.
- `--assets-dir /ruta/a/cutouts_v2`: ubicación de los recortes.
- `--width 1024 --height 576`: resolución de los fondos.
- `--steps 28 --cfg 5.0`: parámetros de generación.

## Ejecutar etapas por separado

Generar un fondo:

```bash
python scripts/run_background.py --episode episode_001 --scene SC001
```

Generar una imagen de escena con referencia:

```bash
python scripts/run_scene.py --episode episode_001 --scene SC001
```

Componer todas las escenas usando fondos ya generados:

```bash
python scripts/compose_episode.py --episode episode_001
```

Generar subtítulos SRT y sus líneas de tiempo estimadas en todos los idiomas:

```bash
python scripts/build_subtitles.py --episode episode_001
```

Preparar el manifiesto de trabajos de voz sin generar audio:

```bash
python scripts/build_voice_manifest.py --episode episode_001
```

### Configurar las voces locales de Huellas Studio

La narración utiliza **CosyVoice 3.0 (0.5B) con Apple Silicon MPS**, mediante el fork comunitario CosyVoice-MPS. No necesita API Key, conexión a ElevenLabs ni créditos por generación. Los diálogos del perro y el gato siguen utilizando Kokoro local.

Instala el runtime aislado de CosyVoice (no modifica el entorno `.venv` principal de Huellas):

```bash
brew install uv
bash scripts/setup_cosyvoice_mps_macos.sh
```

El instalador crea `engines/CosyVoice-MPS/.venv` con Python 3.10 y ofrece descargar una sola vez el modelo `Fun-CosyVoice3-0.5B-2512` (aproximadamente 9.75 GB). El código, el entorno y los pesos quedan fuera del control de versiones.

Instala Kokoro para las voces locales de los personajes, si aún no está instalado:

```bash
bash scripts/setup_tts_macos.sh
```

#### Referencias vocales de Akira y Daniela

Coloca los audios originales, con permiso para clonarlos, en:

- `~/Huellas_Studio_Assets/voice_references/akira_reference.wav`
- `~/Huellas_Studio_Assets/voice_references/daniela_reference.wav`

La referencia debe contener aproximadamente 5–10 segundos de una sola voz, sin música, ruido ni reverberación. El motor la convierte automáticamente a WAV mono de 16 kHz. En `config/tts/production_profiles.json`, completa `reference_text` con la transcripción exacta de cada grabación. La transcripción debe coincidir palabra por palabra con el audio.

#### Generar audiciones locales

```bash
.venv/bin/python scripts/preview_voice_profiles.py --episode episode_001
```

Las audiciones se guardan en `projects/<episode>/audio/voice_previews/`. No consumen créditos externos.

#### Generar las voces del episodio en ambos idiomas

```bash
.venv/bin/python scripts/generate_voice.py --episode episode_001
```

El generador utiliza CosyVoice para Akira/Daniela y Kokoro para los diálogos del perro/gato. Reutiliza WAV existentes cuando coinciden texto, modelo y referencia vocal. Añade `--force` para regenerarlos. Kokoro utiliza MPS automáticamente en Apple Silicon; también puedes indicar `--device cpu`.

Para ejecutar el pipeline de previsualización con voces locales:

```bash
.venv/bin/python scripts/produce_episode_preview.py --episode episode_001 --with-voice
```

La mezcla final se escribe en `audio/<language>/final_mix.wav` y la línea de tiempo real en `audio/<language>/audio_timeline.json`. Si el audio no cabe en la duración de una escena, la síntesis falla explícitamente: no se recorta la voz automáticamente.

**Limitaciones conocidas:** CosyVoice-MPS es un fork comunitario, no el runtime oficial de upstream. El núcleo de inferencia funciona con MPS, pero algunos módulos ONNX se ejecutan en CPU y la generación puede ser más lenta que tiempo real. Es adecuado para producción por lotes, sujeto a la prueba de rendimiento en este Mac.

**Licencias:** el repositorio y la ficha de los pesos indican Apache-2.0. Conserva los avisos de licencia y revisa las condiciones aplicables al uso comercial antes de publicar contenido monetizado. Solo clona voces propias o voces cuyo titular haya autorizado expresamente su uso.

Renderizar un animatic MP4 con las composiciones estáticas y subtítulos:

```bash
python scripts/render_animatic.py --episode episode_001 --language es
```

Si existe `audio/<language>/final_mix.wav`, se incorpora. Si todavía no existe, el animatic lleva una pista silenciosa para revisión visual. No es todavía el vídeo animado final.

Validar traducciones:

```bash
python scripts/validate_bilingual.py --episode episode_001
```

## Estructura de resultados

- `projects/<episode>/backgrounds/`: fondos generados.
- `projects/<episode>/scenes/<scene>/images/`: imágenes generadas con referencia.
- `projects/<episode>/scenes/<scene>/composed/`: composición estática final de cada escena.
- `projects/<episode>/metadata/`: workflow y último resultado por escena.
- `projects/<episode>/metadata/runs/<scene>/`: historial por semilla.
- `projects/<episode>/subtitles/`: subtítulos SRT y líneas de tiempo JSON por idioma.
- `projects/<episode>/audio/<language>/voice_manifest.json`: manifiesto y estado de cada trabajo TTS.
- `projects/<episode>/audio/<language>/final_mix.wav`: mezcla de voz por idioma.
- `projects/<episode>/audio/<language>/audio_timeline.json`: tiempos reales de los clips sintetizados.
- `projects/<episode>/audio/voice_previews/`: audiciones de selección de voces.

## Alcance actual

La etapa automatizada cubre preparación del episodio, validación bilingüe, generación de fondos, composición **estática** de las ocho escenas, narración local con CosyVoice 3 a partir de las referencias autorizadas de Akira y Daniela, diálogos locales de personajes con Kokoro, mezcla de audio y exportación de animatics con subtítulos. La composición usa recortes maestros, por lo que no sustituye la animación de personajes. La sincronización labial, animación, mezcla musical/efectos, control de calidad final y publicación siguen siendo etapas separadas.
