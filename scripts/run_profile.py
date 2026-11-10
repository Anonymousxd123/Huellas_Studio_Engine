import argparse
import json
import random
from pathlib import Path

from huellas_engine.comfy_client import ComfyClient
from huellas_engine.image_utils import prepare_reference_image
from huellas_engine.workflow_manager import load_workflow, prepare_workflow

ROOT = Path(__file__).resolve().parents[1]


def resolve_path(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def main():
    parser = argparse.ArgumentParser("Run Huellas profile")
    parser.add_argument("--profile", required=True, help="Ruta al perfil JSON")
    parser.add_argument("--count", type=int, default=None,
                        help="Override del count del perfil")
    parser.add_argument("--seed", type=int, default=None, help="Seed base")
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    args = parser.parse_args()

    profile_path = resolve_path(args.profile)
    if not profile_path.is_file():
        raise FileNotFoundError(profile_path)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    required = (
        "workflow", "reference", "output_dir", "positive_prompt",
        "negative_prompt", "width", "height", "steps", "cfg",
        "ip_weight", "prefix", "name"
    )
    missing = [key for key in required if key not in profile]
    if missing:
        raise ValueError(f"Faltan campos del perfil: {missing}")

    workflow_path = resolve_path(profile["workflow"])
    reference_path = resolve_path(profile["reference"])
    output_dir = resolve_path(profile["output_dir"])
    if not workflow_path.is_file():
        raise FileNotFoundError(workflow_path)
    if not reference_path.is_file():
        raise FileNotFoundError(reference_path)

    count = args.count if args.count is not None else profile.get("count", 1)
    if not isinstance(count, int) or count < 1:
        raise ValueError("La cantidad de imágenes debe ser un entero mayor que cero")

    width, height = profile["width"], profile["height"]
    if (
        not isinstance(width, int) or not isinstance(height, int)
        or width <= 0 or height <= 0 or width % 8 or height % 8
    ):
        raise ValueError("La resolución debe ser positiva y múltiplo de 8")

    if profile["steps"] < 1 or profile["cfg"] <= 0:
        raise ValueError("Steps debe ser positivo y CFG mayor que cero")

    output_dir.mkdir(parents=True, exist_ok=True)
    prepared_reference = (
        output_dir / ".references"
        / f"{profile['name']}_{width}x{height}.png"
    )
    prepare_reference_image(
        reference_path, prepared_reference, width, height
    )

    client = ComfyClient(args.url)
    client.check()
    workflow_source = load_workflow(workflow_path)
    uploaded_reference = client.upload_image(prepared_reference)

    base_seed = (
        args.seed if args.seed is not None
        else random.randrange(1, 2**32)
    )
    manifest = {
        "profile": str(profile_path),
        "reference": str(reference_path),
        "count": count,
        "base_seed": base_seed,
        "results": []
    }

    for index in range(count):
        seed = base_seed + index
        filename_prefix = f'{profile["prefix"]}_{index + 1:03d}'
        workflow = prepare_workflow(
            workflow_source,
            reference=uploaded_reference,
            prompt=profile["positive_prompt"],
            negative=profile["negative_prompt"],
            seed=seed,
            width=width,
            height=height,
            steps=profile["steps"],
            cfg=profile["cfg"],
            ip_weight=profile["ip_weight"],
            prefix=filename_prefix
        )

        print(f"[{index + 1}/{count}] Enviando {profile['name']} | seed={seed}")
        prompt_id = client.submit(workflow)
        history = client.wait(prompt_id)
        images = client.download_images(history, output_dir)
        if not images:
            raise RuntimeError(
                f"ComfyUI no devolvió imágenes para el trabajo {prompt_id}"
            )

        manifest["results"].append({
            "index": index + 1,
            "seed": seed,
            "prompt_id": prompt_id,
            "images": [str(path) for path in images]
        })
        for image in images:
            print("  Guardada:", image)

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / f'{profile["prefix"]}_manifest.json'
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print("\nLOTE COMPLETADO")
    print("Manifest:", manifest_path)


if __name__ == "__main__":
    main()
