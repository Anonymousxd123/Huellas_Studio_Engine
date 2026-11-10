import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def resolve_path(value, root=ROOT):
    path = Path(value).expanduser()

    if not path.is_absolute():
        path = Path(root) / path

    return path.resolve()


def load_episode(episode_dir):
    path = Path(episode_dir) / "episode.json"
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_characters(episode, profiles_dir=None, root=ROOT):
    """
    Resolve both supported episode formats:
    - Mapping: {"dog": {"reference": "...", "profile": "dog"}}
    - List: ["dog", "cat"] (references are loaded from config/profiles).

    When dog and cat are both listed, the duo profile is loaded as the
    shared reference required by scenes containing both characters.
    """
    raw_characters = episode.get("characters", {})
    profiles_dir = Path(profiles_dir or Path(root) / "config" / "profiles")

    if isinstance(raw_characters, list):
        character_keys = list(raw_characters)

        if {"dog", "cat"}.issubset(character_keys) and "duo" not in character_keys:
            character_keys.append("duo")

        characters = {}
        for key in character_keys:
            profile_path = profiles_dir / f"{key}.json"
            if not profile_path.is_file():
                raise FileNotFoundError(
                    f"No existe el perfil de personaje '{key}': {profile_path}"
                )

            profile_data = json.loads(
                profile_path.read_text(encoding="utf-8")
            )
            characters[key] = {
                "reference": profile_data.get("reference"),
                "profile": profile_data.get("name", key)
            }

    elif isinstance(raw_characters, dict):
        characters = raw_characters

    else:
        raise ValueError(
            "El campo characters debe ser una lista o un objeto"
        )

    resolved = {}

    for key, character in characters.items():
        if not isinstance(character, dict):
            raise ValueError(
                f"Configuración no válida para el personaje '{key}'"
            )

        reference_value = character.get("reference")
        if not reference_value:
            raise ValueError(
                f"Falta la referencia del personaje '{key}'"
            )

        reference = resolve_path(reference_value, root)

        resolved[key] = {
            "reference": str(reference),
            "exists": reference.is_file(),
            "profile": character.get("profile", key)
        }

    return resolved


def resolve_scene(scene, characters):
    names = scene.get("characters", [])

    if not isinstance(names, list):
        raise ValueError(
            f"Los personajes de {scene.get('scene_id', 'la escena')} deben ser una lista"
        )

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
    episode_dir = Path(episode_dir).resolve()
    episode = load_episode(episode_dir)
    project_root = episode_dir.parent.parent

    characters = resolve_characters(
        episode,
        profiles_dir=project_root / "config" / "profiles",
        root=project_root
    )

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
