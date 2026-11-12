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
    parser.add_argument("--modes", choices=["zero_shot", "instruct2"], nargs="+", default=["zero_shot"])
    parser.add_argument("--speeds", type=float, nargs="+", default=[1.0])
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

    style_instructions = {
        "es": (
            "Habla en español latino natural, con una voz cálida, cercana "
            "y conversacional. Usa entonación expresiva pero moderada, "
            "pausas naturales y pronunciación clara. Evita un tono plano."
        ),
        "en": (
            "Speak in natural, warm, friendly conversational English. "
            "Use expressive but restrained intonation, natural pauses, "
            "and clear pronunciation. Avoid a flat, monotone delivery."
        )
    }
    if any(not 0.8 <= speed <= 1.2 for speed in args.speeds):
        raise ValueError("Usa velocidades entre 0.8 y 1.2")

    for language in args.languages:
        if language not in preview_text:
            raise ValueError(f"Idioma de audición no soportado: {language}")
        voice = profile["narration"]["voices"][language]
        jobs = []

        for mode in args.modes:
            for speed in args.speeds:
                speed_label = f"{speed:.2f}".replace(".", "_")
                output = (
                    f"audio/voice_previews/{language}/"
                    f"{voice['name'].lower()}_{mode}_{speed_label}.wav"
                )
                jobs.append({
                    "job_id": f"preview_{language}_{mode}_{speed_label}",
                    "text": preview_text[language],
                    "output": output,
                    "mode": mode,
                    "speed": speed,
                    "instruct_text": style_instructions[language]
                })

        results = synthesize_narration_batch(
            jobs=jobs,
            language=language,
            profile=profile,
            work_dir=episode_dir / "audio" / "voice_previews" / language,
            episode_dir=episode_dir,
            root=ROOT
        )

        for job in jobs:
            result = results[job["job_id"]]
            print(
                f"[OK] {language} | {voice['name']} | "
                f"modo={job['mode']} | speed={job['speed']:.2f} | "
                f"{result['duration_seconds']}s | "
                f"{episode_dir / job['output']}"
            )

    print("\nAUDICIONES LOCALES GENERADAS")


if __name__ == "__main__":
    main()
