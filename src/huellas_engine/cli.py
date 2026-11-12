import argparse
import json
import random
from pathlib import Path

from .comfy_client import ComfyClient
from .image_utils import prepare_reference_image
from .workflow_manager import (
    load_workflow,
    prepare_workflow,
    inspect_workflow
)

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "workflows/image/character_generator_api.json"


def main():
    parser = argparse.ArgumentParser("Huellas Studio Engine")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check")
    check.add_argument("--url", default="http://127.0.0.1:8188")

    inspect = commands.add_parser("inspect")
    inspect.add_argument("--workflow", default=str(WORKFLOW))

    generate = commands.add_parser("generate")
    generate.add_argument("--reference", required=True)
    generate.add_argument("--workflow", default=str(WORKFLOW))
    generate.add_argument("--prompt")
    generate.add_argument("--negative")
    generate.add_argument("--count", type=int, default=1)
    generate.add_argument("--seed", type=int)
    generate.add_argument("--width", type=int, default=1200)
    generate.add_argument("--height", type=int, default=720)
    generate.add_argument("--steps", type=int, default=28)
    generate.add_argument("--cfg", type=float, default=5.5)
    generate.add_argument("--ip-weight", type=float, default=0.6)
    generate.add_argument("--prefix", default="huellas")
    generate.add_argument("--output", default=str(ROOT / "projects/quick_test/images"))
    generate.add_argument("--url", default="http://127.0.0.1:8188")

    args = parser.parse_args()

    if args.command == "check":
        client = ComfyClient(args.url)
        result = client.check()
        print("COMFYUI CONECTADO")
        print(json.dumps(result["queue"], indent=2))
        return

    if args.command == "inspect":
        workflow = load_workflow(args.workflow)
        print(json.dumps(inspect_workflow(workflow), indent=2))
        return

    if args.command == "generate":
        if args.count < 1:
            parser.error("--count debe ser mayor que cero")

        if (
            args.width <= 0 or args.height <= 0
            or args.width % 8 or args.height % 8
        ):
            parser.error("La resolución debe ser positiva y múltiplo de 8")

        output = Path(args.output).expanduser()
        output.mkdir(parents=True, exist_ok=True)
        prepared_reference = (
            output / ".references"
            / f"{args.prefix}_{args.width}x{args.height}.png"
        )
        prepare_reference_image(
            args.reference, prepared_reference, args.width, args.height
        )

        client = ComfyClient(args.url)
        client.check()
        source = load_workflow(args.workflow)

        # Sube la referencia adaptada una sola vez.
        reference = client.upload_image(prepared_reference)

        base_seed = (
            args.seed if args.seed is not None
            else random.randrange(1, 2**32)
        )

        manifest = []

        for index in range(args.count):
            seed = base_seed + index

            workflow = prepare_workflow(
                source,
                reference=reference,
                prompt=args.prompt,
                negative=args.negative,
                seed=seed,
                width=args.width,
                height=args.height,
                steps=args.steps,
                cfg=args.cfg,
                ip_weight=args.ip_weight,
                prefix=f"{args.prefix}_{index + 1:03d}"
            )

            print(f"[{index + 1}/{args.count}] Enviando seed {seed}")

            prompt_id = client.submit(workflow)
            history = client.wait(prompt_id)
            images = client.download_images(history, output)
            if not images:
                raise RuntimeError(
                    f"ComfyUI no devolvió imágenes para el trabajo {prompt_id}"
                )

            for image in images:
                print("Guardada:", image)

            manifest.append({
                "seed": seed,
                "prompt_id": prompt_id,
                "images": [str(p) for p in images]
            })

        output.mkdir(parents=True, exist_ok=True)
        manifest_path = output / f"{args.prefix}_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8"
        )

        print("LOTE FINALIZADO:", manifest_path)


if __name__ == "__main__":
    main()
