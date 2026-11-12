import argparse
from pathlib import Path

from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.scene_composer import DEFAULT_ASSETS, compose_scene

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Huellas Studio Scene Composer")
    parser.add_argument("--episode", default="episode_001",
                        help="ID o ruta del episodio dentro del repositorio")
    parser.add_argument("--scene", required=True)
    parser.add_argument("--background", required=True)
    parser.add_argument("--assets-dir", default=str(DEFAULT_ASSETS))
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()

    if args.width <= 0 or args.height <= 0:
        raise ValueError("La resolución debe ser positiva")

    episode_dir = resolve_episode_dir(args.episode, ROOT)
    output = (
        episode_dir / "scenes" / args.scene / "composed"
        / f"{args.scene}_composed.png"
    )

    compose_scene(
        background_path=args.background,
        output_path=output,
        scene_id=args.scene,
        assets_dir=args.assets_dir,
        width=args.width,
        height=args.height
    )


if __name__ == "__main__":
    main()
