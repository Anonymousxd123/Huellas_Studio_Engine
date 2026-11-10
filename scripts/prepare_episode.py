import json
from pathlib import Path

from huellas_engine.prompt_builder import build_production_plan
from huellas_engine.localization_engine import (
    validate_locales,
    get_languages,
    load_episode_bundle
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode_001"


def main():
    print("\nHUELLAS STUDIO ENGINE")
    print("PREPARACIÓN DEL EPISODIO")
    print("=" * 45)

    errors = validate_locales(EPISODE)

    if errors:
        raise RuntimeError("\n".join(errors))

    for language in get_languages(EPISODE):
        bundle = load_episode_bundle(EPISODE, language)
        print(
            f"Idioma {language}: "
            f"{len(bundle['scenes'])} escenas"
        )

    output, plan = build_production_plan(EPISODE)

    print("\nREFERENCIAS Y PROMPTS")
    print("-" * 45)

    for job in plan["visual_jobs"]:
        print(
            f"{job['scene_id']} | "
            f"{job['reference_key']} | "
            f"{job['status']}"
        )

    print("\nPLAN GENERADO")
    print(output)

    print("\nTOTAL DE ESCENAS:", plan["total_scenes"])
    print("IDIOMAS:", ", ".join(plan["supported_languages"]))

    print("\nPREPARACIÓN COMPLETADA")


if __name__ == "__main__":
    main()
