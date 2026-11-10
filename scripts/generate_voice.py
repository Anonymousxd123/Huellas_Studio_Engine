import argparse
from pathlib import Path

from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.kokoro_engine import synthesize_episode_audio, load_voice_profiles
from huellas_engine.localization_engine import get_languages

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "config" / "tts" / "voice_profiles.json"


def main():
    parser = argparse.ArgumentParser(
        description="Generate local bilingual narration and character dialogue with Kokoro"
    )
    parser.add_argument("--episode", default="episode_001")
    parser.add_argument("--languages", nargs="*",
                        help="Idiomas; por defecto todos los habilitados")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    parser.add_argument("--device", choices=["auto", "cpu", "mps", "cuda"],
                        default="auto")
    parser.add_argument("--line-gap", type=float, default=0.28)
    parser.add_argument("--force", action="store_true",
                        help="Regenerate even if a WAV already exists")
    args = parser.parse_args()

    if args.line_gap < 0:
        raise ValueError("--line-gap no puede ser negativo")

    episode_dir = resolve_episode_dir(args.episode, ROOT)
    profiles = load_voice_profiles(args.profile)
    languages = args.languages or get_languages(episode_dir)

    print("\nHUELLAS STUDIO - KOKORO LOCAL TTS")
    print("=" * 48)
    print("Episodio:", args.episode)
    print("Modelo:", profiles["model"])
    print("Dispositivo:", args.device)

    for language in languages:
        if language not in profiles["languages"]:
            raise ValueError(f"No hay perfil TTS para el idioma {language}")

        result = synthesize_episode_audio(
            episode_dir=episode_dir,
            language=language,
            profile_path=args.profile,
            force=args.force,
            device=args.device,
            line_gap_seconds=args.line_gap
        )
        print(f"\n[OK] Idioma: {language}")
        print("Audios nuevos:", result["generated_jobs"])
        print("Audios reutilizados:", result["reused_jobs"])
        print("Mezcla:", result["mix_path"])
        print("Timeline:", result["timeline_path"])
        print("Manifiesto:", result["manifest_path"])

    print("\nGENERACIÓN TTS COMPLETADA")
    print("Los WAV se guardan localmente dentro del episodio.")


if __name__ == "__main__":
    main()
