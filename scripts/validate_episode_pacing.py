#!/usr/bin/env python3
"""Validate bilingual script pacing before generating audio or video."""
import argparse
from pathlib import Path

from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.pacing_engine import analyze_episode_pacing


ROOT = Path(__file__).resolve().parents[1]


def _clock(seconds):
    whole = round(float(seconds))
    minutes, seconds = divmod(whole, 60)
    return f"{minutes}:{seconds:02d}"


def main():
    parser = argparse.ArgumentParser(
        description="Validate spoken pacing against each scene's duration."
    )
    parser.add_argument("--episode", default="episode_001")
    parser.add_argument("--languages", nargs="*")
    parser.add_argument("--words-per-minute", type=float, default=128.0)
    parser.add_argument("--line-gap", type=float, default=0.28)
    args = parser.parse_args()

    episode_dir = resolve_episode_dir(args.episode, ROOT)
    report = analyze_episode_pacing(
        episode_dir,
        languages=args.languages,
        words_per_minute=args.words_per_minute,
        line_gap_seconds=args.line_gap,
    )

    print("\nHUELLAS STUDIO - SCRIPT PACING VALIDATION")
    print("=" * 52)
    print("Episodio:", episode_dir.name)
    print("Duración objetivo:", _clock(report["target_duration_seconds"]))
    print("Duración de escenas:", _clock(report["planned_duration_seconds"]))
    print("Ritmo de referencia:", f'{report["words_per_minute"]:.0f} palabras/min')
    print("Separación entre clips:", f'{report["line_gap_seconds"]:.2f}s')

    for language, result in report["languages"].items():
        print(
            f"\n[{language.upper()}] {result['total_words']} palabras | "
            f"voz estimada {_clock(result['estimated_voice_seconds'])} | "
            f"cobertura {result['coverage']:.1%}"
        )
        for scene in result["scenes"]:
            print(
                f"  {scene['scene_id']}: {scene['total_words']} palabras | "
                f"{scene['estimated_voice_seconds']:.1f}s/"
                f"{scene['duration_seconds']:.1f}s | "
                f"{scene['utilization']:.1%}"
            )

    if report["errors"]:
        print("\nPACING NO VALIDADO")
        for error in report["errors"]:
            print("[ERROR]", error)
        raise SystemExit(1)

    print("\n[OK] Guiones y duraciones compatibles.")
    print("La duración real se volverá a comprobar al mezclar los WAV.")


if __name__ == "__main__":
    main()
