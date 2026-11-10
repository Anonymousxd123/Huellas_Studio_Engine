import argparse
from pathlib import Path

from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.kokoro_engine import (
    load_voice_profiles,
    synthesize_text_to_file
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "config" / "tts" / "voice_profiles.json"


def main():
    parser = argparse.ArgumentParser(
        description="Generate short narrator voice auditions for Kokoro presets"
    )
    parser.add_argument("--episode", default="episode_001")
    parser.add_argument("--languages", nargs="*",
                        help="Idiomas; por defecto español e inglés")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    parser.add_argument("--device", choices=["auto", "cpu", "mps", "cuda"],
                        default="auto")
    args = parser.parse_args()

    profiles = load_voice_profiles(args.profile)
    languages = args.languages or ["es", "en"]
    episode_dir = resolve_episode_dir(args.episode, ROOT)
    output_root = episode_dir / "audio" / "voice_previews"

    print("\nHUELLAS STUDIO - VOICE AUDITIONS")
    print("=" * 44)

    for language in languages:
        profile = profiles["languages"][language]
        narrator = profile["narrator"]
        candidates = [narrator] + narrator.get("alternatives", [])
        text = profile["preview_text"]

        for candidate in candidates:
            voice_id = candidate["voice_id"]
            output = (
                output_root / language
                / f"{voice_id}_narrator_audition.wav"
            )
            result = synthesize_text_to_file(
                text=text,
                output_path=output,
                lang_code=profile["lang_code"],
                voice_id=voice_id,
                speed=float(candidate.get("speed", 1.0)),
                device=args.device
            )
            print(
                f"[OK] {language} | {voice_id} | "
                f"{result['duration_seconds']}s | {output}"
            )

    print("\nAUDICIONES GENERADAS")
    print("Compara estos WAV con las referencias de Daniela y Akira.")


if __name__ == "__main__":
    main()
