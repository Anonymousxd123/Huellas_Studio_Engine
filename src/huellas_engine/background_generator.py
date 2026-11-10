import copy
import json
import random
from pathlib import Path

from .workflow_manager import load_workflow, node_by_title

ROOT = Path(__file__).resolve().parents[2]

WORKFLOW_PATH = ROOT / "workflows/image/character_generator_api.json"

STYLE = """
Premium 2D animated family cartoon background,
professional animation art direction,
clean polished illustration,
soft cinematic cel shading,
warm harmonious colors,
beautiful environmental storytelling,
consistent animated film aesthetic,
detailed cozy interior,
wide landscape composition,
natural perspective,
soft ambient lighting,
no photorealism, no 3D.
"""

NEGATIVE = """
dog, cat, puppy, kitten, animals, pets,
people, humans, person, character,
animal silhouettes, animal shadows,
faces, eyes, paws, tails,
photorealism, photography, 3D render,
blurry, low quality, distorted perspective,
text, subtitles, watermark, logo.
"""

# Descripciones de escenarios derivadas de las localizaciones
# del episodio y completadas con dirección artística.
BACKGROUND_SCENES = {
    "SC001": """
A cozy family home hallway connected to an open bathroom.
Clearly visible bathroom doorway in the background,
warm wooden flooring, soft cream walls,
subtle bathroom details, welcoming domestic atmosphere.
Keep the foreground and lower central area visually open.
""",

    "SC002": """
Interior of a cozy family house,
a hallway connecting different rooms,
visible bathroom doorway at the end,
warm wooden flooring, cream walls,
natural domestic lighting and clear spatial depth.
Keep the walking path unobstructed.
""",

    "SC003": """
Warm cozy living room,
comfortable sofa, tasteful cushions,
soft rug, coffee table and warm ambient lighting.
Inviting family home atmosphere.
Keep the central foreground open.
""",

    "SC004": """
Cozy living room with a wooden coffee table,
a single clear drinking glass placed on the table,
comfortable sofa in the background,
warm interior lighting and polished wooden details.
Keep the tabletop clearly visible.
""",

    "SC005": """
Welcoming home entrance and front doorway,
wooden entrance door, hallway,
coat hooks and a small entrance console,
warm domestic lighting and inviting atmosphere.
Keep the floor area near the entrance open.
""",

    "SC006": """
Comfortable cozy living room,
large soft sofa with a visible textured blanket,
warm cushions, gentle ambient lighting,
intimate domestic atmosphere.
Keep the sofa and blanket clearly visible.
""",

    "SC007": """
Quiet warm living room,
comfortable sofa, soft cushions,
subtle warm lighting and peaceful atmosphere,
clean uncluttered background,
soft cinematic depth of field.
""",

    "SC008": """
Beautiful welcoming living room,
comfortable sofa, warm decorative lighting,
soft rug and tasteful home decoration,
friendly uplifting atmosphere,
balanced cinematic composition,
open foreground for two characters.
"""
}


def build_background_prompt(scene):
    scene_id = scene["scene_id"]

    if scene_id not in BACKGROUND_SCENES:
        raise ValueError(
            f"No existe descripción de fondo para {scene_id}"
        )

    return f"""
{STYLE}

ENVIRONMENT:
{BACKGROUND_SCENES[scene_id]}

LOCATION FROM EPISODE:
{scene.get('location', '')}

COMPOSITION:
Single wide establishing background.
Landscape 16:9.
Eye-level camera.
No animals or people.
No characters.
Keep important environmental details visible.
Leave clear foreground space for character compositing.
No written text.
""".strip()


def prepare_background_workflow(
    source,
    prompt,
    seed,
    width=1024,
    height=576,
    steps=28,
    cfg=5.0,
    prefix="huellas_background"
):
    workflow = copy.deepcopy(source)

    positive = node_by_title(workflow, "Positive Prompt")
    negative = node_by_title(workflow, "Negative Prompt")
    sampler = node_by_title(workflow, "KSampler")
    latent = node_by_title(workflow, "Empty Latent")
    save = node_by_title(workflow, "Save Image")

    positive["inputs"]["text"] = prompt
    negative["inputs"]["text"] = NEGATIVE.strip()

    sampler["inputs"].update({
        "seed": seed,
        "steps": steps,
        "cfg": cfg,
        "denoise": 1.0
    })

    latent["inputs"].update({
        "width": width,
        "height": height,
        "batch_size": 1
    })

    # Conectar SDXL directamente al KSampler.
    checkpoint_id = next(
        node_id for node_id, node in workflow.items()
        if node.get("_meta", {}).get("title") == "Load Checkpoint"
    )

    latent_id = next(
        node_id for node_id, node in workflow.items()
        if node.get("_meta", {}).get("title") == "Empty Latent"
    )

    sampler["inputs"]["model"] = [checkpoint_id, 0]
    sampler["inputs"]["latent_image"] = [latent_id, 0]

    save["inputs"]["filename_prefix"] = prefix

    # Eliminar IP-Adapter y la referencia de personajes.
    remove_titles = {
        "Load Image",
        "IPAdapter Unified Loader",
        "IPAdapter Advanced"
    }

    remove_ids = [
        node_id for node_id, node in workflow.items()
        if node.get("_meta", {}).get("title") in remove_titles
    ]

    for node_id in remove_ids:
        del workflow[node_id]

    return workflow


def save_background_metadata(
    episode_id,
    scene_id,
    prompt_id,
    seed,
    prompt,
    images,
    width,
    height
):
    metadata_dir = ROOT / "projects" / episode_id / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "episode_id": episode_id,
        "scene_id": scene_id,
        "prompt_id": prompt_id,
        "seed": seed,
        "prompt": prompt,
        "width": width,
        "height": height,
        "images": [str(image) for image in images],
        "status": "completed"
    }

    output = metadata_dir / f"{scene_id}_background.json"

    output.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return output
