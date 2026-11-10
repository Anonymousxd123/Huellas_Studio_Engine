import argparse
import json
from pathlib import Path

from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.localization_engine import (
    validate_locales,
    load_episode_bundle,
    get_languages
)

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser("Huellas Bilingual Validator")
    parser.add_argument("--episode", default="episode_001",
                        help="ID o ruta del episodio dentro del repositorio")
    args = parser.parse_args()

    episode_dir = resolve_episode_dir(args.episode, ROOT)
    errors = validate_locales(episode_dir)
    if errors:
        print("ERRORES DE LOCALIZACIÓN:")
        for error in errors:
            print("-", error)
        raise SystemExit(1)

    print("LOCALIZACIÓN VALIDADA")
    for language in get_languages(episode_dir):
        bundle = load_episode_bundle(episode_dir, language)
        result = {
            "language": language,
            "title": bundle["title"],
            "scenes": len(bundle["scenes"]),
            "duration_seconds": sum(
                scene["duration_seconds"] for scene in bundle["scenes"]
            )
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))

    print("\nIDIOMAS VALIDADOS")


if __name__ == "__main__":
    main()
