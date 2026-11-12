import argparse

from huellas_engine.animation_engine import (
    DEFAULT_COMFYUI_DIR,
    animate_scene,
)


def main():
    parser = argparse.ArgumentParser(
        description="Genera un clip piloto de movimiento LTX para una escena Huellas."
    )
    parser.add_argument("--episode", default="episode_001")
    parser.add_argument("--scene", default="SC003")
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--comfyui-dir", default=str(DEFAULT_COMFYUI_DIR))
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=288)
    parser.add_argument("--frames", type=int, default=49)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--seed", type=int, default=20261112)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()

    animate_scene(
        episode_id=args.episode,
        scene_id=args.scene,
        url=args.url,
        comfyui_dir=args.comfyui_dir,
        width=args.width,
        height=args.height,
        frames=args.frames,
        fps=args.fps,
        seed=args.seed,
        ffmpeg=args.ffmpeg,
    )


if __name__ == "__main__":
    main()
