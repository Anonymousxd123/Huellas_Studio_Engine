import argparse
import json
import random
from pathlib import Path

from huellas_engine.background_generator import (
    WORKFLOW_PATH,
    build_background_prompt,
    prepare_background_workflow,
    save_background_metadata
)
from huellas_engine.comfy_client import ComfyClient
from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.localization_engine import validate_locales
from huellas_engine.prompt_builder import build_production_plan
from huellas_engine.scene_composer import DEFAULT_ASSETS, SCENE_LAYOUTS, compose_scene
from huellas_engine.scene_engine import load_episode, validate_episode
from huellas_engine.workflow_manager import load_workflow

ROOT = Path(__file__).resolve().parents[1]


def existing_background(episode_dir, scene_id):
    metadata_path = episode_dir / "metadata" / f"{scene_id}_background.json"
    if not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for value in reversed(metadata.get("images", [])):
        path = Path(value).expanduser()
        if path.is_file():
            return path
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Generate all episode backgrounds and compose all scenes"
    )
    parser.add_argument("--episode", default="episode_001")
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--assets-dir", default=str(DEFAULT_ASSETS))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=576)
    parser.add_argument("--steps", type=int, default=28)
    parser.add_argument("--cfg", type=float, default=5.0)
    parser.add_argument("--scenes", nargs="*", help="IDs opcionales; por defecto todas las escenas")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate backgrounds even when valid outputs exist")
    args = parser.parse_args()

    if (
        args.width <= 0 or args.height <= 0
        or args.width % 8 or args.height % 8
        or args.steps < 1 or args.cfg <= 0
    ):
        raise ValueError("Resolución, steps o CFG no válidos")

    episode_dir = resolve_episode_dir(args.episode, ROOT)
    episode = load_episode(episode_dir / "episode.json")

    episode_errors = validate_episode(episode)
    locale_errors = validate_locales(episode_dir)
    errors = episode_errors + locale_errors
    if errors:
        raise RuntimeError("\n".join(errors))

    requested = set(args.scenes or [])
    scenes = [
        scene for scene in episode["scenes"]
        if not requested or scene["scene_id"] in requested
    ]
    found_ids = {scene["scene_id"] for scene in scenes}
    if requested - found_ids:
        raise ValueError(f"Escenas desconocidas: {sorted(requested - found_ids)}")
    if not scenes:
        raise ValueError("No hay escenas seleccionadas")
    missing_layouts = [
        scene["scene_id"] for scene in scenes
        if scene["scene_id"] not in SCENE_LAYOUTS
    ]
    if missing_layouts:
        raise ValueError(f"Faltan layouts de composición: {missing_layouts}")

    # This also verifies that all character references can be resolved.
    plan_path, plan = build_production_plan(episode_dir)
    print("Plan de producción:", plan_path)

    assets_dir = Path(args.assets_dir).expanduser()
    required_assets = [
        assets_dir / "dog_master_rgba.png",
        assets_dir / "cat_master_rgba.png"
    ]
    missing_assets = [path for path in required_assets if not path.is_file()]
    if missing_assets:
        raise FileNotFoundError(
            "Faltan recortes de personajes. Ejecuta "
            "scripts/build_character_assets.py. Archivos: "
            + ", ".join(str(path) for path in missing_assets)
        )

    client = ComfyClient(args.url)
    client.check()
    workflow_source = load_workflow(WORKFLOW_PATH)

    base_seed = (
        args.seed if args.seed is not None
        else random.randrange(1, 2**32)
    )
    backgrounds = []
    print("\nHUELLAS STUDIO - AUTOMATED EPISODE COMPOSITOR")
    print("=" * 54)
    print("Episodio:", episode["episode_id"])
    print("Escenas:", len(scenes))
    print("Seed base:", base_seed)

    for index, scene in enumerate(scenes):
        scene_id = scene["scene_id"]
        existing = None if args.force else existing_background(episode_dir, scene_id)

        if existing:
            print(f"[{index + 1}/{len(scenes)}] {scene_id}: fondo existente, se reutiliza")
            backgrounds.append((scene_id, existing))
            continue

        seed = base_seed + index
        prompt = build_background_prompt(scene)
        workflow = prepare_background_workflow(
            workflow_source,
            prompt=prompt,
            seed=seed,
            width=args.width,
            height=args.height,
            steps=args.steps,
            cfg=args.cfg,
            prefix=f"huellas_bg_{scene_id}_{seed}"
        )

        metadata_dir = episode_dir / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        workflow_path = metadata_dir / f"{scene_id}_background_workflow.json"
        workflow_path.write_text(
            json.dumps(workflow, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        print(f"[{index + 1}/{len(scenes)}] {scene_id}: generando fondo | seed={seed}")
        prompt_id = client.submit(workflow)
        history = client.wait(prompt_id)
        images = client.download_images(
            history, episode_dir / "backgrounds"
        )
        if not images:
            raise RuntimeError(f"ComfyUI no generó fondo para {scene_id}")

        save_background_metadata(
            episode_id=episode["episode_id"],
            scene_id=scene_id,
            prompt_id=prompt_id,
            seed=seed,
            prompt=prompt,
            images=images,
            width=args.width,
            height=args.height
        )
        backgrounds.append((scene_id, images[-1]))

    print("\nCOMPONIENDO ESCENAS")
    for index, (scene_id, background) in enumerate(backgrounds, 1):
        output = (
            episode_dir / "scenes" / scene_id / "composed"
            / f"{scene_id}_composed.png"
        )
        print(f"[{index}/{len(backgrounds)}] {scene_id}")
        compose_scene(
            background_path=background,
            output_path=output,
            scene_id=scene_id,
            assets_dir=assets_dir,
            width=1280,
            height=720
        )

    print("\nPRODUCCIÓN VISUAL ESTÁTICA COMPLETADA")
    print("Escenas compuestas:", len(backgrounds))
    print("Directorio:", episode_dir / "scenes")


if __name__ == "__main__":
    main()
