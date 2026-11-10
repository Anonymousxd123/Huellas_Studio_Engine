import json
import sys
from pathlib import Path

from huellas_engine.comfy_client import ComfyClient
from huellas_engine.workflow_manager import load_workflow, node_by_title

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode_001"
PLAN = EPISODE / "scenes/production_plan.json"
WORKFLOW = ROOT / "workflows/image/character_generator_api.json"

REQUIRED = {
    "Load Image": ["image"],
    "Positive Prompt": ["text"],
    "Negative Prompt": ["text"],
    "KSampler": ["seed", "steps", "cfg"],
    "Empty Latent": ["width", "height"],
    "IPAdapter Advanced": ["weight"],
    "Save Image": ["filename_prefix"],
    "Load Checkpoint": ["ckpt_name"]
}


def main():
    errors = []

    print("\nHUELLAS STUDIO - PRODUCTION PREFLIGHT")
    print("=" * 48)

    # 1. Archivos
    for path in [PLAN, WORKFLOW]:
        if path.exists():
            print("[OK] Archivo:", path.name)
        else:
            errors.append(f"Archivo inexistente: {path}")

    if errors:
        raise RuntimeError("\n".join(errors))

    # 2. Workflow
    workflow = load_workflow(WORKFLOW)

    print("\nWORKFLOW")
    print("-" * 48)

    for title, required_inputs in REQUIRED.items():
        try:
            node = node_by_title(workflow, title)
            inputs = node.get("inputs", {})

            missing = [
                key for key in required_inputs
                if key not in inputs
            ]

            if missing:
                errors.append(
                    f"{title}: faltan entradas {missing}"
                )
            else:
                print(f"[OK] {title}: {required_inputs}")

            if title == "Load Checkpoint":
                print(
                    "     Checkpoint:",
                    inputs["ckpt_name"]
                )

        except ValueError as error:
            errors.append(str(error))

    # 3. Plan de producción
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    jobs = plan.get("visual_jobs", [])

    print("\nPRODUCTION PLAN")
    print("-" * 48)
    print("Episodio:", plan["episode_id"])
    print("Escenas:", len(jobs))

    for job in jobs:
        reference = Path(job["reference_path"])

        if not reference.is_file():
            errors.append(
                f"{job['scene_id']}: referencia inexistente: {reference}"
            )
        elif not job.get("prompt"):
            errors.append(
                f"{job['scene_id']}: prompt vacío"
            )
        else:
            print(
                f"[OK] {job['scene_id']} | "
                f"{job['reference_key']} | "
                f"{job['width']}x{job['height']}"
            )

    if len(jobs) != 8:
        errors.append(f"Se esperaban 8 escenas, encontradas {len(jobs)}")

    # 4. ComfyUI
    print("\nCOMFYUI")
    print("-" * 48)

    try:
        client = ComfyClient()
        status = client.check()

        print("[OK] Conexión establecida")
        print("Cola:", status["queue"])

    except Exception as error:
        errors.append(f"ComfyUI: {error}")

    # Resultado
    print("\n" + "=" * 48)

    if errors:
        print("PREFLIGHT FALLIDO")
        for error in errors:
            print("[ERROR]", error)
        sys.exit(1)

    print("PREFLIGHT CORRECTO")
    print("Listos para la primera escena piloto.")


if __name__ == "__main__":
    main()
