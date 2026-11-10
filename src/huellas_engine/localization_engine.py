import json
from pathlib import Path


def load_episode_bundle(episode_dir, language="es"):
    episode_dir = Path(episode_dir)

    episode_path = episode_dir / "episode.json"
    locale_path = episode_dir / "locales" / f"{language}.json"

    if not episode_path.exists():
        raise FileNotFoundError(episode_path)

    if not locale_path.exists():
        raise FileNotFoundError(
            f"No existe traducción para: {language}"
        )

    episode = json.loads(
        episode_path.read_text(encoding="utf-8")
    )

    locale = json.loads(
        locale_path.read_text(encoding="utf-8")
    )

    if language not in episode.get("supported_languages", []):
        raise ValueError(f"Idioma no habilitado: {language}")

    result = dict(episode)
    result["language"] = language
    result["title"] = locale["episode"]["title"]
    result["description"] = locale["episode"]["description"]

    localized_scenes = []

    for scene in episode["scenes"]:
        scene_id = scene["scene_id"]

        if scene_id not in locale["scenes"]:
            raise ValueError(
                f"Falta traducción de la escena {scene_id}"
            )

        localized = dict(scene)
        localized.update(locale["scenes"][scene_id])

        localized_scenes.append(localized)

    result["scenes"] = localized_scenes

    return result


def validate_locales(episode_dir):
    episode_dir = Path(episode_dir)

    episode = json.loads(
        (episode_dir / "episode.json").read_text(encoding="utf-8")
    )

    expected_ids = {
        scene["scene_id"] for scene in episode["scenes"]
    }

    errors = []

    for language in episode["supported_languages"]:
        locale_path = (
            episode_dir / "locales" / f"{language}.json"
        )

        if not locale_path.exists():
            errors.append(f"Falta archivo: {locale_path}")
            continue

        locale = json.loads(
            locale_path.read_text(encoding="utf-8")
        )

        localized_ids = set(locale.get("scenes", {}))

        for scene_id in expected_ids - localized_ids:
            errors.append(
                f"{language}: falta escena {scene_id}"
            )

        for scene_id in localized_ids - expected_ids:
            errors.append(
                f"{language}: escena desconocida {scene_id}"
            )

        for scene_id in expected_ids & localized_ids:
            scene = locale["scenes"][scene_id]

            if not scene.get("title"):
                errors.append(f"{language}/{scene_id}: falta título")

            if not scene.get("narration"):
                errors.append(f"{language}/{scene_id}: falta narración")

            if not isinstance(scene.get("dialogue"), list):
                errors.append(f"{language}/{scene_id}: diálogo inválido")
                continue

            for index, dialogue in enumerate(scene["dialogue"]):
                if not dialogue.get("character") or not dialogue.get("text"):
                    errors.append(
                        f"{language}/{scene_id}: diálogo {index + 1} incompleto"
                    )

    return errors


def get_languages(episode_dir):
    episode_dir = Path(episode_dir)

    episode = json.loads(
        (episode_dir / "episode.json").read_text(encoding="utf-8")
    )

    return episode.get("supported_languages", [])
