import argparse
import json
from pathlib import Path

from huellas_engine.audio_engine import build_voice_manifest
from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.localization_engine import get_languages

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(
        description="Prepare provider-neutral TTS manifests for an episode"
    )
    parser.add_argument("--episode", default="episode_001")
    parser.add_argument("--languages", nargs="*",
                        help="Idiomas; por defecto todos los habilitados")
    parser.add_argument("--words-per-minute", type=int, default=150)
    args = parser.parse_args()

    episode_dir = resolve_episode_dir(args.episode, ROOT)
    languages = args.languages or get_languages(episode_dir)

    print("\nHUELLAS STUDIO - VOICE JOB PREPARATION")
    print("=" * 48)
    for language in languages:
        path, manifest = build_voice_manifest(
            episode_dir,
            language,
            words_per_minute=args.words_per_minute
        )
        print(
            f"[OK] {language}: {manifest['total_jobs']} trabajos de voz"
        )
        print(path)

    print("\nMANIFIESTOS DE VOZ PREPARADOS")
    print("La generación de audio queda pendiente de configurar el proveedor y las voces.")


if __name__ == "__main__":
    main()
