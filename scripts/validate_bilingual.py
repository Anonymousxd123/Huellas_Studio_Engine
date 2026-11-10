import json
from pathlib import Path

from huellas_engine.localization_engine import (
    validate_locales,
    load_episode_bundle,
    get_languages
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode_001"

errors = validate_locales(EPISODE)

if errors:
    print("ERRORES DE LOCALIZACIÓN:")
    for error in errors:
        print("-", error)
    raise SystemExit(1)

print("LOCALIZACIÓN VALIDADA")

for language in get_languages(EPISODE):
    bundle = load_episode_bundle(EPISODE, language)

    result = {
        "language": language,
        "title": bundle["title"],
        "scenes": len(bundle["scenes"]),
        "duration_seconds": sum(
            scene["duration_seconds"]
            for scene in bundle["scenes"]
        )
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))

print("\nAMBOS IDIOMAS ESTÁN LISTOS")
