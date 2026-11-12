import argparse
import json
from pathlib import Path

from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.scene_composer import DEFAULT_ASSETS, compose_scene

ROOT = Path(__file__).resolve().parents[1]


def find_background(episode_dir, scene_id):
    metadata_path = episode_dir / "metadata" / f"{scene_id}_background.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
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

    assets_dir = Path(args.assets_dir).expanduser()
    missing_assets = [
        assets_dir / name
        for name in ("dog_master_rgba.png", "cat_master_rgba.png")
        if not (assets_dir / name).is_file()
    ]
    if missing_assets:
        raise FileNotFoundError(
            "Faltan recortes de personajes: "
            + ", ".join(str(path) for path in missing_assets)
        )

    # Resolve every input first so missing backgrounds never leave a
    # partially composed episode.
    tasks = []
    for scene in scenes:
        scene_id = scene["scene_id"]
        background = find_background(episode_dir, scene_id)
        output = (
            episode_dir / "scenes" / scene_id / "composed"
            / f"{scene_id}_composed.png"
        )
        tasks.append((scene_id, background, output))

    print("\nHUELLAS STUDIO - EPISODE COMPOSER")
    print("=" * 48)
    print("Episodio:", episode["episode_id"])
    print("Escenas:", len(tasks))

    for index, (scene_id, background, output) in enumerate(tasks, 1):
        print(f"\n[{index}/{len(tasks)}] {scene_id}")
        compose_scene(
            background_path=background,
            output_path=output,
            scene_id=scene_id,
            assets_dir=assets_dir,
            width=args.width,
            height=args.height
        )

    print("\nCOMPOSICIÓN DEL EPISODIO COMPLETADA")
    for _, _, output in tasks:
        print(output)


if __name__ == "__main__":
    main()
