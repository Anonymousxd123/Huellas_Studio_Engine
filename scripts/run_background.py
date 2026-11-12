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
from huellas_engine.workflow_manager import load_workflow

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(
        description="Huellas Studio Background Generator"
    )
    parser.add_argument("--episode", default="episode_001",
                        help="ID o ruta del episodio dentro del repositorio")
    parser.add_argument("--scene", required=True)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=576)
    parser.add_argument("--steps", type=int, default=28)
    parser.add_argument("--cfg", type=float, default=5.0)
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    args = parser.parse_args()

    if args.width <= 0 or args.height <= 0 or args.width % 8 or args.height % 8:
        raise ValueError("Ancho y alto deben ser positivos y múltiplos de 8")
    if args.steps < 1 or args.cfg <= 0:
        raise ValueError("Steps debe ser positivo y CFG mayor que cero")

    episode_dir = resolve_episode_dir(args.episode, ROOT)
    episode = json.loads(
        (episode_dir / "episode.json").read_text(encoding="utf-8")
    )
    scenes = [
        scene for scene in episode["scenes"]
        if scene["scene_id"] == args.scene
    ]
    if len(scenes) != 1:
        raise ValueError(f"Escena inexistente o duplicada: {args.scene}")

    scene = scenes[0]
    seed = args.seed if args.seed is not None else random.randrange(1, 2**32)
    prompt = build_background_prompt(scene)

    output_dir = episode_dir / "backgrounds"
    metadata_dir = episode_dir / "metadata"
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    print("\nHUELLAS STUDIO - BACKGROUND GENERATOR")
    print("=" * 48)
    print("Episodio:", episode["episode_id"])
    print("Escena:", args.scene)
    print("Localización:", scene.get("location"))
    print("Resolución:", f"{args.width}x{args.height}")
    print("Seed:", seed)

    client = ComfyClient(args.url)
    client.check()
    print("[OK] ComfyUI conectado")

    source = load_workflow(WORKFLOW_PATH)
    workflow = prepare_background_workflow(
        source,
        prompt=prompt,
        seed=seed,
        width=args.width,
        height=args.height,
        steps=args.steps,
        cfg=args.cfg,
        prefix=f"huellas_bg_{args.scene}_{seed}"
    )

    workflow_file = metadata_dir / f"{args.scene}_background_workflow.json"
    workflow_file.write_text(
        json.dumps(workflow, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print("[OK] Workflow preparado. Nodos:", len(workflow))

    prompt_id = client.submit(workflow)
    print("Prompt ID:", prompt_id)
    print("Generando escenario...")
    history = client.wait(prompt_id)
    images = client.download_images(history, output_dir)
    if not images:
        raise RuntimeError("No se generó ningún fondo")

    metadata = save_background_metadata(
        episode_id=episode["episode_id"],
        scene_id=args.scene,
        prompt_id=prompt_id,
        seed=seed,
        prompt=prompt,
        images=images,
        width=args.width,
        height=args.height
    )

    print("\nFONDO GENERADO")
    for image in images:
        print(image)
    print("Metadata:", metadata)


if __name__ == "__main__":
    main()
