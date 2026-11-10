import argparse
from pathlib import Path

from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.localization_engine import (
    validate_locales,
    get_languages,
    load_episode_bundle
)
from huellas_engine.prompt_builder import build_production_plan

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser("Huellas Studio Episode Preparation")
    parser.add_argument("--episode", default="episode_001",
                        help="ID o ruta del episodio dentro del repositorio")
    args = parser.parse_args()

    episode_dir = resolve_episode_dir(args.episode, ROOT)
    print("\nHUELLAS STUDIO ENGINE")
    print("PREPARACIÓN DEL EPISODIO")
    print("=" * 45)
    print("Episodio:", episode_dir.name)

    errors = validate_locales(episode_dir)
    if errors:
        raise RuntimeError("\n".join(errors))

    for language in get_languages(episode_dir):
        bundle = load_episode_bundle(episode_dir, language)
        print(f"Idioma {language}: {len(bundle['scenes'])} escenas")

    output, plan = build_production_plan(episode_dir)

    print("\nREFERENCIAS Y PROMPTS")
    print("-" * 45)
    for job in plan["visual_jobs"]:
        print(f"{job['scene_id']} | {job['reference_key']} | {job['status']}")

    print("\nPLAN GENERADO")
    print(output)
    print("\nTOTAL DE ESCENAS:", plan["total_scenes"])
    print("IDIOMAS:", ", ".join(plan["supported_languages"]))
    print("\nPREPARACIÓN COMPLETADA")


if __name__ == "__main__":
    main()
