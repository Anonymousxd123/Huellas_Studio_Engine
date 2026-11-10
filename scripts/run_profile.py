import argparse
import json
import random
from pathlib import Path

from huellas_engine.comfy_client import ComfyClient
from huellas_engine.workflow_manager import load_workflow, prepare_workflow

def expand(path_str: str) -> Path:
    return Path(path_str).expanduser().resolve()

def main():
    parser = argparse.ArgumentParser("Run Huellas profile")
    parser.add_argument("--profile", required=True, help="Ruta al perfil JSON")
    parser.add_argument("--count", type=int, default=None, help="Override del count del perfil")
    parser.add_argument("--seed", type=int, default=None, help="Seed base")
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    args = parser.parse_args()

    profile_path = expand(args.profile)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    workflow_path = expand(profile["workflow"])
    reference_path = expand(profile["reference"])
    output_dir = expand(profile["output_dir"])

    client = ComfyClient(args.url)
    workflow_source = load_workflow(workflow_path)

    uploaded_reference = client.upload_image(reference_path)

    count = args.count if args.count is not None else profile.get("count", 1)
    base_seed = args.seed if args.seed is not None else random.randrange(1, 2**32)

    manifest = {
        "profile": str(profile_path),
        "reference": str(reference_path),
        "count": count,
        "base_seed": base_seed,
        "results": []
    }

    for i in range(count):
        seed = base_seed + i
        filename_prefix = f'{profile["prefix"]}_{i+1:03d}'

        wf = prepare_workflow(
            workflow_source,
            reference=uploaded_reference,
            prompt=profile["positive_prompt"],
            negative=profile["negative_prompt"],
            seed=seed,
            width=profile["width"],
            height=profile["height"],
            steps=profile["steps"],
            cfg=profile["cfg"],
            ip_weight=profile["ip_weight"],
            prefix=filename_prefix
        )

        print(f"[{i+1}/{count}] Enviando {profile['name']} | seed={seed}")
        prompt_id = client.submit(wf)
        history = client.wait(prompt_id)
        images = client.download_images(history, output_dir)

        manifest["results"].append({
            "index": i + 1,
            "seed": seed,
            "prompt_id": prompt_id,
            "images": [str(p) for p in images]
        })

        for img in images:
            print("  Guardada:", img)

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / f'{profile["prefix"]}_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("\nLOTE COMPLETADO")
    print("Manifest:", manifest_path)

if __name__ == "__main__":
    main()
