import argparse
from pathlib import Path

from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.subtitle_engine import write_subtitles

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(
        description="Build estimated SRT subtitles for every episode language"
    )
    parser.add_argument("--episode", default="episode_001")
    parser.add_argument("--languages", nargs="*",
                        help="Idiomas; por defecto todos los habilitados")
    parser.add_argument("--chars-per-second", type=float, default=15.0)
    parser.add_argument("--max-chars", type=int, default=42)
    parser.add_argument("--max-lines", type=int, default=2)
    args = parser.parse_args()

    episode_dir = resolve_episode_dir(args.episode, ROOT)
    outputs = write_subtitles(
        episode_dir,
        languages=args.languages,
        chars_per_second=args.chars_per_second,
        max_chars=args.max_chars,
        max_lines=args.max_lines
    )

    print("\nSUBTÍTULOS GENERADOS")
    for output in outputs:
        print(output)
    print("\nNOTA: los tiempos son estimaciones desde el texto; deben ajustarse")
    print("contra el audio final cuando se incorpore la etapa de voz.")


if __name__ == "__main__":
    main()
