import argparse
from pathlib import Path

from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.pacing_engine import analyze_episode_pacing
from huellas_engine.localization_engine import get_languages
from huellas_engine.tts_engine import (
    load_production_profile,
    synthesize_episode_audio
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "config" / "tts" / "production_profiles.json"


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate bilingual narration with local CosyVoice 3 and "
            "character dialogue with local Kokoro"
        )
    )
    parser.add_argument("--episode", default="episode_001")
    parser.add_argument("--languages", nargs="*",
                        help="Idiomas; por defecto todos los habilitados")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    parser.add_argument("--kokoro-profile",
                        help="Sobrescribe el perfil local de voces Kokoro")
    parser.add_argument("--device", choices=["auto", "cpu", "mps", "cuda"],
                        default="auto",
                        help="Dispositivo para diálogos Kokoro")
    parser.add_argument("--line-gap", type=float, default=0.28)
    parser.add_argument("--pacing-wpm", type=float, default=128.0,
                        help="Ritmo de referencia para validar la duración del guion")
    parser.add_argument("--force", action="store_true",
                        help="Regenera los WAV aunque exista una caché válida")
    args = parser.parse_args()

    if args.line_gap < 0:
        raise ValueError("--line-gap no puede ser negativo")

    episode_dir = resolve_episode_dir(args.episode, ROOT)
    profile = load_production_profile(args.profile)
    languages = args.languages or get_languages(episode_dir)
    pacing = analyze_episode_pacing(
        episode_dir,
        languages=languages,
        words_per_minute=args.pacing_wpm,
        line_gap_seconds=args.line_gap
    )
    if pacing["errors"]:
        print("\\nPACING NO VALIDADO")
        for error in pacing["errors"]:
            print("[ERROR]", error)
        raise SystemExit(1)
    for language, report in pacing["languages"].items():
        print(
            f"[PACING] {language}: {report['total_words']} palabras | "
            f"{report['estimated_voice_seconds']:.1f}s estimados | "
            f"{report['coverage']:.1%} del episodio"
        )

    print("\nHUELLAS STUDIO - LOCAL TTS")
    print("=" * 52)
    print("Episodio:", args.episode)
    print("Narración: CosyVoice 3 local (MPS)")
    print("Modelo:", profile["narration"]["model_id"])
    print("Akira: referencia local en inglés")
    print("Daniela: referencia local en español")
    print("Diálogos: Kokoro local")
    print("Sin API externa ni créditos por generación.")

    for language in languages:
        result = synthesize_episode_audio(
            episode_dir=episode_dir,
            language=language,
            profile_path=args.profile,
            kokoro_profile_path=args.kokoro_profile,
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

    print("\nGENERACIÓN TTS LOCAL COMPLETADA")


if __name__ == "__main__":
    main()
