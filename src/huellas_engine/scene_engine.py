import json
import re
from pathlib import Path


def create_episode(root, episode_id, title):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", episode_id):
        raise ValueError("ID de episodio no válido")

    root = Path(root).resolve()
    folder = root / "projects" / episode_id

    if (folder / "episode.json").exists():
        raise FileExistsError("El episodio ya existe")

    for name in [
        "assets", "scenes", "audio",
        "subtitles", "renders", "final", "metadata", "locales"
    ]:
        (folder / name).mkdir(parents=True, exist_ok=True)

    profiles_dir = root / "config" / "profiles"
    characters = {}
    for key in ("dog", "cat", "duo"):
        profile_path = profiles_dir / f"{key}.json"
        if not profile_path.is_file():
            continue
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        characters[key] = {
            "name": profile.get("name", key),
            "reference": profile.get("reference", ""),
            "profile": key
        }

    episode = {
        "schema_version": 1,
        "episode_id": episode_id,
        "title": title,
        "channel": "Ah Mira Ese Dato",
        "target_duration_seconds": 600,
        "visual_style": "2d_cartoon",
        "resolution": "1920x1080",
        "fps": 24,
        "characters": characters,
        "scenes": [],
        "default_language": "es",
        "supported_languages": ["es", "en"],
        "shared_visual_assets": True,
        "localization_strategy": "shared_visuals_separate_audio"
    }

    path = folder / "episode.json"
    path.write_text(
        json.dumps(episode, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    return path


def load_episode(path):
    path = Path(path)
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def validate_episode(episode):
    errors = []
    scenes = episode.get("scenes", [])

    if not isinstance(scenes, list):
        return ["El campo scenes debe ser una lista"]

    if not scenes:
        errors.append("El episodio no contiene escenas")

    ids = set()
    total_duration = 0

    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            errors.append(f"Escena {index}: formato no válido")
            continue

        scene_id = scene.get("scene_id")

        if not scene_id:
            errors.append(f"Escena {index}: falta scene_id")
        elif scene_id in ids:
            errors.append(f"ID duplicado: {scene_id}")
        else:
            ids.add(scene_id)

        duration = scene.get("duration_seconds")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or duration <= 0
        ):
            errors.append(f"Escena {index}: duración no válida")
        else:
            total_duration += duration

        for field in ["location", "characters", "action", "visual_prompt"]:
            if not scene.get(field):
                errors.append(f"Escena {index}: falta {field}")

        characters = scene.get("characters", [])
        if not isinstance(characters, list):
            errors.append(f"Escena {index}: characters debe ser una lista")

    target = episode.get("target_duration_seconds")
    if isinstance(target, (int, float)) and target > 0 and scenes:
        if total_duration > target * 1.25:
            errors.append(
                f"La duración de escenas ({total_duration}s) supera "
                f"el objetivo del episodio ({target}s) en más de 25%"
            )

    return errors


def build_storyboard(episode_path):
    episode_path = Path(episode_path)
    episode = load_episode(episode_path)
    errors = validate_episode(episode)

    if errors:
        raise ValueError("\n".join(errors))

    total_duration = sum(
        scene["duration_seconds"]
        for scene in episode["scenes"]
    )

    storyboard = {
        "episode_id": episode["episode_id"],
        "title": episode["title"],
        "total_scenes": len(episode["scenes"]),
        "total_duration_seconds": total_duration,
        "scenes": episode["scenes"]
    }

    output = episode_path.parent / "storyboard.json"
    output.write_text(
        json.dumps(storyboard, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    return output
