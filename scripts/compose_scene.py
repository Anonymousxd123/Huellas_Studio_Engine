import argparse
from pathlib import Path

from huellas_engine.scene_composer import compose_scene

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(
        description="Huellas Studio Scene Composer"
    )

    parser.add_argument("--scene", required=True)
    parser.add_argument("--background", required=True)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)

    args = parser.parse_args()

    output = (
        ROOT / "projects/episode_001/scenes"
        / args.scene / "composed"
        / f"{args.scene}_composed.png"
    )

    compose_scene(
        background_path=args.background,
        output_path=output,
        scene_id=args.scene,
        width=args.width,
        height=args.height
    )


if __name__ == "__main__":
    main()
