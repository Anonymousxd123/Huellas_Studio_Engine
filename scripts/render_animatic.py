import argparse
from pathlib import Path

from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.video_engine import render_animatic

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(
        description="Render a static-scene animatic with optional audio and subtitles"
    )
    parser.add_argument("--episode", default="episode_001")
    parser.add_argument("--language", default="es")
    parser.add_argument("--output")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--require-audio", action="store_true",
                        help="Fail if the final voice mix is not available")
    args = parser.parse_args()

    episode_dir = resolve_episode_dir(args.episode, ROOT)
    output = render_animatic(
        episode_dir,
        args.language,
        output_path=args.output,
        ffmpeg=args.ffmpeg,
        fps=args.fps,
        width=args.width,
        height=args.height,
        allow_silent=not args.require_audio
    )
    print("\nANIMATIC RENDERIZADO")
    print(output)


if __name__ == "__main__":
    main()
