import argparse
import json
import sys
from pathlib import Path

from huellas_engine.comfy_client import ComfyClient
from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.localization_engine import validate_locales
from huellas_engine.pacing_engine import analyze_episode_pacing
from huellas_engine.scene_engine import load_episode
from huellas_engine.workflow_manager import load_workflow, node_by_title

ROOT = Path(__file__).resolve().parents[1]
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
    parser = argparse.ArgumentParser("Huellas Studio Production Preflight")
    parser.add_argument("--episode", default="episode_001",
                        help="ID o ruta del episodio dentro del repositorio")
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--skip-comfyui", action="store_true",
                        help="Validar archivos sin exigir que ComfyUI esté activo")
    parser.add_argument("--pacing-wpm", type=float, default=128.0)
    parser.add_argument("--line-gap", type=float, default=0.28)
    args = parser.parse_args()

    errors = []
    episode_dir = resolve_episode_dir(args.episode, ROOT)
    episode_path = episode_dir / "episode.json"
    plan_path = episode_dir / "scenes" / "production_plan.json"

    print("\nHUELLAS STUDIO - PRODUCTION PREFLIGHT")
    print("=" * 48)
    print("Episodio:", episode_dir.name)

    for path in (episode_path, plan_path, WORKFLOW):
        if path.is_file():
            print("[OK] Archivo:", path)
        else:
            errors.append(f"Archivo inexistente: {path}")

    if errors:
        raise RuntimeError("\n".join(errors))

    locale_errors = validate_locales(episode_dir)
    errors.extend(locale_errors)
    if not locale_errors:
        pacing = analyze_episode_pacing(
            episode_dir,
            words_per_minute=args.pacing_wpm,
            line_gap_seconds=args.line_gap
        )
        print("\\nSCRIPT PACING")
        print("-" * 48)
        for language, report in pacing["languages"].items():
            print(
                f"[OK] {language}: {report['total_words']} palabras | "
                f"{report['estimated_voice_seconds']:.1f}s estimados | "
                f"{report['coverage']:.1%} del episodio"
            )
        errors.extend(pacing["errors"])

    workflow = load_workflow(WORKFLOW)
    print("\nWORKFLOW")
    print("-" * 48)
    for title, required_inputs in REQUIRED.items():
        try:
            node = node_by_title(workflow, title)
            missing = [key for key in required_inputs if key not in node.get("inputs", {})]
            if missing:
                errors.append(f"{title}: faltan entradas {missing}")
            else:
                print(f"[OK] {title}: {required_inputs}")
        except ValueError as error:
            errors.append(str(error))

    episode = load_episode(episode_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    jobs = plan.get("visual_jobs", [])
    expected_ids = [scene.get("scene_id") for scene in episode.get("scenes", [])]
    actual_ids = [job.get("scene_id") for job in jobs]

    print("\nPRODUCTION PLAN")
    print("-" * 48)
    print("Escenas esperadas:", len(expected_ids))
    print("Trabajos preparados:", len(jobs))

    if len(actual_ids) != len(set(actual_ids)):
        errors.append("El plan contiene scene_id duplicados")
    if set(expected_ids) != set(actual_ids):
        errors.append(
            f"El plan no coincide con el episodio. "
            f"Faltan: {sorted(set(expected_ids) - set(actual_ids))}; "
            f"sobran: {sorted(set(actual_ids) - set(expected_ids))}"
        )

    for job in jobs:
        scene_id = job.get("scene_id", "UNKNOWN")
        reference = Path(job.get("reference_path", "")).expanduser()
        if not reference.is_file():
            errors.append(f"{scene_id}: referencia inexistente: {reference}")
        if not job.get("prompt"):
            errors.append(f"{scene_id}: prompt vacío")
        if not job.get("negative_prompt"):
            errors.append(f"{scene_id}: negative prompt vacío")
        width, height = job.get("width"), job.get("height")
        if (
            not isinstance(width, int) or not isinstance(height, int)
            or width <= 0 or height <= 0 or width % 8 or height % 8
        ):
            errors.append(f"{scene_id}: resolución inválida")
        else:
            print(f"[OK] {scene_id} | {job.get('reference_key')} | {width}x{height}")

    if not args.skip_comfyui:
        print("\nCOMFYUI")
        print("-" * 48)
        try:
            status = ComfyClient(args.url).check()
            print("[OK] Conexión establecida")
            print("Cola:", status["queue"])
        except Exception as error:
            errors.append(f"ComfyUI: {error}")
    else:
        print("\n[SKIP] ComfyUI: validación offline solicitada")

    print("\n" + "=" * 48)
    if errors:
        print("PREFLIGHT FALLIDO")
        for error in errors:
            print("[ERROR]", error)
        sys.exit(1)

    print("PREFLIGHT CORRECTO")
    print("Listos para la producción visual.")


if __name__ == "__main__":
    main()
