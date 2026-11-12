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
    parser.add_argument("--modes", choices=["zero_shot", "instruct2"], nargs="+", default=["zero_shot", "instruct2"])
    parser.add_argument("--speeds", type=float, nargs="+", default=[1.0])
    args = parser.parse_args()

    profile = load_cosyvoice_profile(args.profile)
    episode_dir = resolve_episode_dir(args.episode, ROOT)

    preview_text = {
        "es": (
            "Hay pequeños detalles de nuestras mascotas que pueden contarnos "
            "mucho más de lo que imaginamos. Cuando un perro inclina la cabeza "
            "para escuchar un sonido, intenta comprender qué está pasando. "
            "Cuando un gato nos sigue de una habitación a otra, quizá "
            "simplemente busca compañía. Sus gestos, sus sonidos y sus rutinas "
            "forman parte de una manera muy especial de comunicarse. Si "
            "observamos con paciencia, aprendemos a reconocer lo que necesitan "
            "y a respetar su personalidad. En Huellas Studio descubrimos esas "
            "señales cotidianas y compartimos consejos sencillos para cuidar "
            "mejor a nuestros compañeros. Porque convivir con ellos también "
            "significa aprender a entenderlos cada día un poquito más."
        ),
        "en": (
            "Small everyday moments can tell us a surprising amount about the "
            "animals who share our homes. A dog may tilt his head when he hears "
            "an unfamiliar sound, while a cat might follow us from one room to "
            "another simply because it enjoys our company. Their gestures, "
            "sounds, and routines are all part of the way they communicate. "
            "When we slow down and pay attention, we become better at "
            "understanding what they need and respecting their individual "
            "personalities. Here at Huellas Studio, we explore these familiar "
            "habits and share simple ideas for caring for our pets. Because "
            "living together becomes even more rewarding when we learn to "
            "understand one another."
        )
    }

    print("\nHUELLAS STUDIO - LOCAL VOICE AUDITIONS")
    print("=" * 52)
    print("Motor: CosyVoice 3.0 local")
    print("No consume créditos de ElevenLabs.")

    style_instructions = {
        "es": (
            "Habla en español latino con una voz femenina cálida y "
            "conversacional. Conserva la identidad y el timbre de la "
            "referencia. Usa entonación natural, énfasis moderados y pausas "
            "orgánicas. Evita una interpretación plana o de locutora exagerada."
        ),
        "en": (
            "Speak in natural, warm, conversational English. Preserve the "
            "reference speaker's masculine voice identity, timbre, and accent. "
            "Use varied but restrained intonation, clear articulation, and "
            "natural pauses. Avoid a flat or exaggerated announcer style."
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
