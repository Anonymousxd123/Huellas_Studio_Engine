import argparse
import json
import random
from pathlib import Path

from PIL import Image

from huellas_engine.comfy_client import ComfyClient
from huellas_engine.workflow_manager import (
    load_workflow,
    prepare_workflow
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode_001"
PLAN = EPISODE / "scenes/production_plan.json"
WORKFLOW = ROOT / "workflows/image/character_generator_api.json"


def prepare_reference(source, destination, width, height):
    from PIL import Image, ImageFilter

    with Image.open(source) as original:
        image = original.convert("RGB")

        # Ajustar sin recortar ni deformar.
        scale = min(
            width / image.width,
            height / image.height
        )

        new_width = round(image.width * scale)
        new_height = round(image.height * scale)

        resized = image.resize(
            (new_width, new_height),
            Image.Resampling.LANCZOS
        )

        # Fondo extendido y desenfocado.
        background = image.resize(
            (width, height),
            Image.Resampling.LANCZOS
        ).filter(ImageFilter.GaussianBlur(radius=24))

        # Centrar imagen original completa.
        x = (width - new_width) // 2
        y = (height - new_height) // 2

        background.paste(resized, (x, y))

        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        background.save(destination, format="PNG")

        print(
            f"[OK] Referencia adaptada: "
            f"{image.width}x{image.height} -> "
            f"{width}x{height}"
        )

    return destination


def main():
    parser = argparse.ArgumentParser("Huellas Scene Runner")

    parser.add_argument("--scene", required=True)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--denoise", type=float, default=0.25)
    parser.add_argument(
        "--latent-mode",
        choices=["reference", "noise"],
        default="reference"
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8188"
    )

    args = parser.parse_args()

    if not 0 <= args.denoise <= 1:
        raise ValueError("Denoise debe estar entre 0 y 1")

    plan = json.loads(PLAN.read_text(encoding="utf-8"))

    jobs = [
        job for job in plan["visual_jobs"]
        if job["scene_id"] == args.scene
    ]

    if len(jobs) != 1:
        raise ValueError(
            f"Escena inexistente o duplicada: {args.scene}"
        )

    job = jobs[0]

    reference = Path(job["reference_path"]).expanduser()

    if not reference.is_file():
        raise FileNotFoundError(reference)

    width = args.width or job["width"]
    height = args.height or job["height"]

    if width % 8 or height % 8:
        raise ValueError("Ancho y alto deben ser múltiplos de 8")

    seed = (
        args.seed
        if args.seed is not None
        else random.randrange(1, 2**32)
    )

    output_dir = EPISODE / "scenes" / args.scene / "images"
    metadata_dir = EPISODE / "metadata"

    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    print("\nHUELLAS STUDIO - SCENE RUNNER")
    print("=" * 45)
    print("Escena:", args.scene)
    print("Referencia original:", reference)
    print("Resolución:", f"{width}x{height}")
    print("Seed:", seed)
    print("Latent mode:", args.latent_mode)
    print("Denoise:", args.denoise)

    prepared_reference = (
        metadata_dir /
        f"{args.scene}_reference_{width}x{height}.png"
    )

    prepare_reference(
        reference,
        prepared_reference,
        width,
        height
    )

    print("[OK] Referencia preparada:", prepared_reference)

    client = ComfyClient(args.url)
    client.check()

    print("[OK] ComfyUI conectado")

    source = load_workflow(WORKFLOW)

    uploaded_reference = client.upload_image(prepared_reference)

    print("[OK] Referencia subida:", uploaded_reference)

    workflow = prepare_workflow(
        source,
        reference=uploaded_reference,
        prompt=job["prompt"],
        negative=job["negative_prompt"],
        seed=seed,
        width=width,
        height=height,
        steps=job["steps"],
        cfg=job["cfg"],
        ip_weight=job["ip_weight"],
        prefix=f"huellas_{args.scene}_{seed}",
        denoise=args.denoise,
        latent_mode=args.latent_mode
    )

    workflow_path = metadata_dir / f"{args.scene}_workflow.json"

    workflow_path.write_text(
        json.dumps(workflow, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("[OK] Workflow preparado")

    sampler = workflow[
        next(
            key for key, value in workflow.items()
            if value.get("_meta", {}).get("title") == "KSampler"
        )
    ]

    print(
        "[OK] KSampler latent:",
        sampler["inputs"]["latent_image"]
    )

    prompt_id = client.submit(workflow)

    print("Prompt ID:", prompt_id)
    print("Esperando generación...")

    history = client.wait(prompt_id)
    images = client.download_images(history, output_dir)

    if not images:
        raise RuntimeError(
            "ComfyUI terminó sin devolver imágenes"
        )

    metadata = {
        "episode_id": "episode_001",
        "scene_id": args.scene,
        "prompt_id": prompt_id,
        "seed": seed,
        "reference_original": str(reference),
        "reference_prepared": str(prepared_reference),
        "reference_uploaded": uploaded_reference,
        "latent_mode": args.latent_mode,
        "denoise": args.denoise,
        "width": width,
        "height": height,
        "steps": job["steps"],
        "cfg": job["cfg"],
        "ip_weight": job["ip_weight"],
        "prompt": job["prompt"],
        "negative_prompt": job["negative_prompt"],
        "images": [str(image) for image in images],
        "status": "completed"
    }

    metadata_path = metadata_dir / f"{args.scene}_run.json"

    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("\nGENERACIÓN COMPLETADA")

    for image in images:
        print("Imagen:", image)

    print("Metadata:", metadata_path)


if __name__ == "__main__":
    main()
