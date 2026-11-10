import argparse
from pathlib import Path

from huellas_engine.cosyvoice_engine import (
    load_cosyvoice_profile,
    synthesize_narration_batch
)
from huellas_engine.episode_paths import resolve_episode_dir

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "config" / "tts" / "production_profiles.json"


def main():
    parser = argparse.ArgumentParser(
        description="Generate local voice-cloning auditions for Akira and Daniela"
    )
    parser.add_argument("--episode", default="episode_001")
    parser.add_argument("--languages", nargs="*", default=["es", "en"])
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    args = parser.parse_args()

    profile = load_cosyvoice_profile(args.profile)
    episode_dir = resolve_episode_dir(args.episode, ROOT)

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

    print("\nHUELLAS STUDIO - LOCAL VOICE AUDITIONS")
    print("=" * 52)
    print("Motor: CosyVoice 3.0 local")
    print("No consume créditos de ElevenLabs.")

    for language in args.languages:
        if language not in preview_text:
            raise ValueError(f"Idioma de audición no soportado: {language}")
        voice = profile["narration"]["voices"][language]
        output = (
            f"audio/voice_previews/{language}/"
            f"{voice['name'].lower()}_cosyvoice_audition.wav"
        )
        job = {
            "job_id": f"preview_{language}",
            "text": preview_text[language],
            "output": output
        }
        results = synthesize_narration_batch(
            jobs=[job],
            language=language,
            profile=profile,
            work_dir=episode_dir / "audio" / "voice_previews" / language,
            episode_dir=episode_dir,
            root=ROOT
        )
        result = results[job["job_id"]]
        print(
            f"[OK] {language} | {voice['name']} | "
            f"{result['duration_seconds']}s | "
            f"{episode_dir / output}"
        )

    print("\nAUDICIONES LOCALES GENERADAS")


if __name__ == "__main__":
    main()
