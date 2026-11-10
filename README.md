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

El siguiente comando genera los fondos que falten y compone todas las escenas:

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

## Alcance actual

La etapa automatizada cubre preparación del episodio, validación bilingüe, generación de fondos y composición **estática** de las ocho escenas. La composición usa recortes maestros, por lo que no sustituye la animación de personajes. El pipeline de voz, sincronización labial, animación, montaje de vídeo y publicación se desarrollará como etapas separadas.
