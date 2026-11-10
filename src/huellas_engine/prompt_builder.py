import json
from pathlib import Path

from .asset_resolver import resolve_episode_assets, load_episode

ROOT = Path(__file__).resolve().parents[2]

STYLE_LOCK = """
Premium 2D animated family cartoon,
polished professional animation,
clean dark outlines,
beautiful expressive faces,
soft cinematic cel shading,
warm harmonious colors,
consistent character proportions,
high quality animated film illustration,
detailed cozy environments,
landscape 16:9 composition,
single coherent still frame,
no photorealism, no 3D.
"""

CHARACTER_LOCK = {
    "dog": """
Golden retriever cartoon dog.
Golden honey fur, cream muzzle and chest,
floppy golden ears, warm DARK BROWN eyes,
blue collar and round GOLD medallion.
Preserve the exact reference appearance.
""",
    "cat": """
Gray tabby cartoon cat.
Gray striped fur, pure white chest,
large GREEN eyes, pink nose,
upright pointed ears and feline proportions.
Preserve the exact reference appearance.
""",
    "duo": """
EXACTLY TWO MAIN CHARACTERS:

CHARACTER 1 - DOG:
Golden retriever, golden honey fur,
cream muzzle and chest, floppy ears,
warm DARK BROWN eyes,
blue collar and round GOLD medallion.

CHARACTER 2 - CAT:
Gray tabby cat, gray striped fur,
white chest, large GREEN eyes,
pink nose and pointed ears.

Both must match the supplied reference image.
Never merge, replace or redesign them.
"""
}

SCENE_OVERRIDES = {
    "SC001": {
        "scene": """
A cozy home hallway with an open bathroom doorway.
The bathroom is clearly recognizable in the background.
Warm welcoming interior, cinematic animated environment.
""",
        "action": """
The gray tabby cat is walking toward the open bathroom
doorway, looking back with a curious expression.
The golden retriever is sitting in the hallway,
watching the cat with a surprised and curious expression.
The human owner remains OFF CAMERA.
""",
        "composition": """
EXACTLY TWO ANIMALS, BOTH FULLY VISIBLE.

DOG ON THE LEFT SIDE OF THE IMAGE.
CAT ON THE RIGHT SIDE OF THE IMAGE.

Both characters must be visible simultaneously,
from the top of their ears to their paws and tails.
Both have clear silhouettes and distinct bodies.
Keep both characters at similar visual scale.
Leave safe margins around both characters.

Single wide establishing shot.
Eye-level camera.
No closeups, no split screen, no sequence of shots.
"""
    }
}

NEGATIVE_PROMPT = """
one animal, single animal, only one character,
dog alone, cat alone, missing dog, missing cat,
missing second character, invisible cat, invisible dog,
extra animals, duplicate dogs, duplicate cats,
merged characters, overlapping bodies,
cropped characters, cropped head, cropped paws,
character outside frame, cut off tail,
wrong fur color, wrong eye color,
green dog eyes, blue dog eyes,
brown cat eyes, missing blue collar,
missing gold medallion, different character design,
deformed anatomy, extra legs, extra paws,
extra limbs, photorealistic, photography,
3D render, blurry, low quality,
text, subtitles, watermark, logo.
"""


def build_prompt(scene, reference_key):
    scene_id = scene["scene_id"]

    character_description = CHARACTER_LOCK.get(
        reference_key, CHARACTER_LOCK["duo"]
    )

    override = SCENE_OVERRIDES.get(scene_id)

    if override:
        visual_scene = override["scene"]
        action = override["action"]
        composition = override["composition"]
    else:
        visual_scene = scene.get("visual_prompt", "")
        action = scene.get("action", "")
        composition = """
Single wide cinematic composition.
All required characters visible simultaneously.
Preserve their reference identities.
"""

    return f"""
{STYLE_LOCK}

CHARACTER IDENTITY:
{character_description}

SCENE:
{visual_scene}

ACTION:
{action}

COMPOSITION:
{composition}

STRICT CHARACTER CONSISTENCY:
Use the supplied reference image as the identity source.
Preserve exact fur colors, eye colors, facial features,
collars, accessories and body proportions.

Do not omit either main character.
No written text inside the image.
""".strip()


def build_production_plan(episode_dir):
    episode_dir = Path(episode_dir)

    episode = load_episode(episode_dir)
    assets = resolve_episode_assets(episode_dir)

    if assets["errors"]:
        raise RuntimeError("\n".join(assets["errors"]))

    asset_index = {
        item["scene_id"]: item
        for item in assets["scenes"]
    }

    jobs = []

    for scene in episode["scenes"]:
        resolved = asset_index[scene["scene_id"]]

        jobs.append({
            "job_id": f"visual_{scene['scene_id']}",
            "scene_id": scene["scene_id"],
            "duration_seconds": scene["duration_seconds"],
            "reference_key": resolved["reference_key"],
            "reference_path": resolved["reference_path"],
            "prompt": build_prompt(
                scene, resolved["reference_key"]
            ),
            "negative_prompt": NEGATIVE_PROMPT.strip(),
            "width": 1280,
            "height": 720,
            "steps": 30,
            "cfg": 5.0,
            "ip_weight": 0.80,
            "status": "prepared"
        })

    plan = {
        "episode_id": episode["episode_id"],
        "title": episode["title"],
        "supported_languages": episode["supported_languages"],
        "shared_visual_assets": True,
        "total_scenes": len(jobs),
        "visual_jobs": jobs
    }

    output = episode_dir / "scenes" / "production_plan.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    output.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return output, plan
