import json
from pathlib import Path


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON inválido en {path}: {error}") from error


def load_episode_bundle(episode_dir, language="es"):
    episode_dir = Path(episode_dir)
    episode_path = episode_dir / "episode.json"
    locale_path = episode_dir / "locales" / f"{language}.json"

    if not episode_path.is_file():
        raise FileNotFoundError(episode_path)
    if not locale_path.is_file():
        raise FileNotFoundError(f"No existe traducción para: {language}")

    episode = _read_json(episode_path)
    locale = _read_json(locale_path)

    if language not in episode.get("supported_languages", []):
        raise ValueError(f"Idioma no habilitado: {language}")

    locale_episode = locale.get("episode")
    if not isinstance(locale_episode, dict):
        raise ValueError(f"{language}: falta el bloque episode")
    for field in ("title", "description"):
        if not locale_episode.get(field):
            raise ValueError(f"{language}: falta episode.{field}")

    locale_scenes = locale.get("scenes")
    if not isinstance(locale_scenes, dict):
        raise ValueError(f"{language}: el bloque scenes debe ser un objeto")

    result = dict(episode)
    result["language"] = language
    result["title"] = locale_episode["title"]
    result["description"] = locale_episode["description"]

    localized_scenes = []
    for scene in episode.get("scenes", []):
        scene_id = scene["scene_id"]
        localized_data = locale_scenes.get(scene_id)
        if not isinstance(localized_data, dict):
            raise ValueError(f"Falta traducción de la escena {scene_id}")

        localized = dict(scene)
        localized.update(localized_data)
        localized_scenes.append(localized)

    result["scenes"] = localized_scenes
    return result


def validate_locales(episode_dir):
    episode_dir = Path(episode_dir)
    episode_path = episode_dir / "episode.json"
    if not episode_path.is_file():
        return [f"Falta archivo: {episode_path}"]

    try:
        episode = _read_json(episode_path)
    except ValueError as error:
        return [str(error)]

    languages = episode.get("supported_languages", [])
    if not isinstance(languages, list) or not languages:
        return ["El episodio debe declarar supported_languages como lista no vacía"]

    scenes = episode.get("scenes", [])
    if not isinstance(scenes, list):
        return ["El campo scenes del episodio debe ser una lista"]

    expected_ids = set()
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict) or not scene.get("scene_id"):
            return [f"Escena {index}: falta scene_id válido"]
        expected_ids.add(scene["scene_id"])

    errors = []
    for language in languages:
        locale_path = episode_dir / "locales" / f"{language}.json"
        if not locale_path.is_file():
            errors.append(f"Falta archivo: {locale_path}")
            continue

        try:
            locale = _read_json(locale_path)
        except ValueError as error:
            errors.append(str(error))
            continue

        if not isinstance(locale, dict):
            errors.append(f"{language}: el archivo de idioma debe contener un objeto")
            continue

        declared_language = locale.get("language")
        if declared_language and declared_language != language:
            errors.append(
                f"{language}: el campo language declara '{declared_language}'"
            )

        locale_episode = locale.get("episode")
        if not isinstance(locale_episode, dict):
            errors.append(f"{language}: falta el bloque episode")
        else:
            for field in ("title", "description"):
                if not locale_episode.get(field):
                    errors.append(f"{language}: falta episode.{field}")

        localized_scenes = locale.get("scenes")
        if not isinstance(localized_scenes, dict):
            errors.append(f"{language}: el bloque scenes debe ser un objeto")
            continue

        localized_ids = set(localized_scenes)
        for scene_id in expected_ids - localized_ids:
            errors.append(f"{language}: falta escena {scene_id}")
        for scene_id in localized_ids - expected_ids:
            errors.append(f"{language}: escena desconocida {scene_id}")

        for scene_id in expected_ids & localized_ids:
            scene = localized_scenes[scene_id]
            if not isinstance(scene, dict):
                errors.append(f"{language}/{scene_id}: la escena debe ser un objeto")
                continue

            if not scene.get("title"):
                errors.append(f"{language}/{scene_id}: falta título")
            if not scene.get("narration"):
                errors.append(f"{language}/{scene_id}: falta narración")

            dialogue = scene.get("dialogue")
            if not isinstance(dialogue, list):
                errors.append(f"{language}/{scene_id}: diálogo inválido")
                continue

            for index, line in enumerate(dialogue, 1):
                if (
                    not isinstance(line, dict)
                    or not line.get("character")
                    or not line.get("text")
                ):
                    errors.append(
                        f"{language}/{scene_id}: diálogo {index} incompleto"
                    )

    return errors


def get_languages(episode_dir):
    episode_dir = Path(episode_dir)
    episode = _read_json(episode_dir / "episode.json")
    return episode.get("supported_languages", [])
