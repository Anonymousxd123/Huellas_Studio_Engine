import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def resolve_path(value):
    path = Path(value).expanduser()

    if not path.is_absolute():
        path = ROOT / path

    return path.resolve()


def load_episode(episode_dir):
    path = Path(episode_dir) / "episode.json"
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_characters(episode):
    resolved = {}

    for key, character in episode["characters"].items():
        reference = resolve_path(character["reference"])

        resolved[key] = {
            "reference": str(reference),
            "exists": reference.is_file(),
            "profile": character.get("profile", key)
        }

    return resolved


def resolve_scene(scene, characters):
    names = scene.get("characters", [])

    if "duo" in names or {"dog", "cat"}.issubset(names):
        selected = "duo"
    elif len(names) == 1:
        selected = names[0]
    else:
        selected = "duo"

    if selected not in characters:
        raise ValueError(
            f"Referencia no configurada: {selected}"
        )

    character = characters[selected]

    if not character["exists"]:
        raise FileNotFoundError(
            f"Referencia inexistente: {character['reference']}"
        )

    return {
        "reference_key": selected,
        "reference_path": character["reference"],
        "characters": names
    }


def resolve_episode_assets(episode_dir):
    episode = load_episode(episode_dir)
    characters = resolve_characters(episode)

    scenes = []
    errors = []

    for scene in episode["scenes"]:
        try:
            result = resolve_scene(scene, characters)

            scenes.append({
                "scene_id": scene["scene_id"],
                **result
            })

        except (ValueError, FileNotFoundError) as error:
            errors.append(str(error))

    return {
        "characters": characters,
        "scenes": scenes,
        "errors": errors
    }
