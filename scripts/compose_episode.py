import argparse
import json
from pathlib import Path

from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.scene_composer import DEFAULT_ASSETS, compose_scene

ROOT = Path(__file__).resolve().parents[1]


def find_background(episode_dir, scene_id):
    metadata_path = episode_dir / "metadata" / f"{scene_id}_background.json"
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        for value in reversed(metadata.get("images", [])):
            candidate = Path(value).expanduser()
            if candidate.is_file():
                return candidate

    candidates = sorted(
        (episode_dir / "backgrounds").glob(f"*{scene_id}*.png"),
        key=lambda path: path.stat().st_mtime,
        reverse=True
    )
    if candidates:
        return candidates[0]

    raise FileNotFoundError(
        f"No se encontró fondo para {scene_id}. Genera primero el fondo."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Compose every scene of an episode automatically"
    )
    parser.add_argument("--episode", default="episode_001",
                        help="ID o ruta del episodio dentro del repositorio")
    parser.add_argument("--assets-dir", default=str(DEFAULT_ASSETS))
    parser.add_argument("--scenes", nargs="*",
                        help="IDs opcionales; por defecto compone todas las escenas")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()

    if args.width <= 0 or args.height <= 0:
        raise ValueError("La resolución debe ser positiva")

    episode_dir = resolve_episode_dir(args.episode, ROOT)
    episode = json.loads(
        (episode_dir / "episode.json").read_text(encoding="utf-8")
    )
    requested = set(args.scenes or [])
    scenes = [
        scene for scene in episode.get("scenes", [])
        if not requested or scene.get("scene_id") in requested
    ]

    if requested:
        found = {scene.get("scene_id") for scene in scenes}
        missing = requested - found
        if missing:
            raise ValueError(f"Escenas desconocidas: {sorted(missing)}")
    if not scenes:
        raise ValueError("El episodio no contiene escenas para componer")

    print("\nHUELLAS STUDIO - EPISODE COMPOSER")
    print("=" * 48)
    print("Episodio:", episode["episode_id"])
    print("Escenas:", len(scenes))

    completed = []
    for index, scene in enumerate(scenes, 1):
        scene_id = scene["scene_id"]
        background = find_background(episode_dir, scene_id)
        output = (
            episode_dir / "scenes" / scene_id / "composed"
            / f"{scene_id}_composed.png"
        )
        print(f"\n[{index}/{len(scenes)}] {scene_id}")
        compose_scene(
            background_path=background,
            output_path=output,
            scene_id=scene_id,
            assets_dir=args.assets_dir,
            width=args.width,
            height=args.height
        )
        completed.append(output)

    print("\nCOMPOSICIÓN DEL EPISODIO COMPLETADA")
    for path in completed:
        print(path)


if __name__ == "__main__":
    main()
