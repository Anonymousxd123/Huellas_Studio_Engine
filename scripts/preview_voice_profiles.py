import argparse
from pathlib import Path

from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.tts_engine import load_production_profile
from huellas_engine.elevenlabs_engine import synthesize_text_to_file

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "config" / "tts" / "production_profiles.json"


def main():
    parser = argparse.ArgumentParser(
        description="Generate short auditions using the original ElevenLabs narrators"
    )
    parser.add_argument("--episode", default="episode_001")
    parser.add_argument("--languages", nargs="*",
                        help="Idiomas; por defecto español e inglés")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    args = parser.parse_args()

    profile = load_production_profile(args.profile)
    languages = args.languages or ["es", "en"]
    episode_dir = resolve_episode_dir(args.episode, ROOT)
    output_root = episode_dir / "audio" / "voice_previews"

    preview_text = {
        "es": (
            "Hola. Hoy vamos a descubrir algunos comportamientos de perros "
            "y gatos que quizá has interpretado mal. Quédate hasta el final, "
            "porque entender mejor a nuestras mascotas puede cambiar la "
            "forma en que las cuidamos."
        ),
        "en": (
            "Hello. Today we're going to discover some dog and cat behaviors "
            "you may have misunderstood. Stay until the end, because "
            "understanding our pets better can change the way we care for them."
        )
    }

    print("\nHUELLAS STUDIO - ELEVENLABS VOICE AUDITIONS")
    print("=" * 52)
    print("Estas pruebas consumen créditos de ElevenLabs.")

    for language in languages:
        narrator = profile["narration"]["voices"][language]
        output = (
            output_root / language
            / f"{narrator['name'].lower()}_elevenlabs_audition.wav"
        )
        result = synthesize_text_to_file(
            text=preview_text[language],
            output_path=output,
            voice_id=narrator["voice_id"],
            model_id=profile["narration"]["model_id"]
        )
        print(
            f"[OK] {language} | {narrator['name']} | "
            f"{result['duration_seconds']}s | {output}"
        )

    print("\nAUDICIONES ORIGINALES GENERADAS")
    print("Escucha los WAV para confirmar las voces antes de producir el episodio.")


if __name__ == "__main__":
    main()
