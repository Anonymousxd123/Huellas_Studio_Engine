import json
import re
from pathlib import Path


def create_episode(root, episode_id, title):

    if not re.fullmatch(r"[a-zA-Z0-9_-]+", episode_id):
        raise ValueError("ID de episodio no válido")

    folder = Path(root) / "projects" / episode_id

    if (folder / "episode.json").exists():
        raise FileExistsError("El episodio ya existe")

    for name in [
        "assets", "scenes", "audio",
        "subtitles", "renders", "final", "metadata"
    ]:
        (folder / name).mkdir(parents=True, exist_ok=True)

    episode = {
        "schema_version": 1,
        "episode_id": episode_id,
        "title": title,
        "language": "es",
        "target_duration_seconds": 600,
        "visual_style": "2d_cartoon",
        "characters": ["dog", "cat"],
        "scenes": []
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

    if not scenes:
        errors.append("El episodio no contiene escenas")

    ids = set()

    for index, scene in enumerate(scenes, 1):

        scene_id = scene.get("scene_id")

        if not scene_id:
            errors.append(f"Escena {index}: falta scene_id")
        elif scene_id in ids:
            errors.append(f"ID duplicado: {scene_id}")
        else:
            ids.add(scene_id)

        if not isinstance(scene.get("duration_seconds"), (int, float)) \
                or scene["duration_seconds"] <= 0:
            errors.append(f"Escena {index}: duración no válida")

        for field in [
            "location", "characters",
            "action", "visual_prompt"
        ]:
            if not scene.get(field):
                errors.append(
                    f"Escena {index}: falta {field}"
                )

    return errors


def build_storyboard(episode_path):

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

    output = Path(episode_path).parent / "storyboard.json"

    output.write_text(
        json.dumps(storyboard, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return output