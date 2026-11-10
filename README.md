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

Preparar el manifiesto de trabajos de voz para TTS:

```bash
python scripts/build_voice_manifest.py --episode episode_001
```

El manifiesto separa narración y diálogos por personaje y deja la integración con el proveedor TTS desacoplada.

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
- `projects/<episode>/audio/<language>/voice_manifest.json`: trabajos de voz pendientes de proveedor TTS.

## Alcance actual

La etapa automatizada cubre preparación del episodio, validación bilingüe, generación de fondos y composición **estática** de las ocho escenas. La composición usa recortes maestros, por lo que no sustituye la animación de personajes. El pipeline de voz, sincronización labial, animación, montaje de vídeo y publicación se desarrollará como etapas separadas.
