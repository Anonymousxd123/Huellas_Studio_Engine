import json
import re
import shutil
import subprocess
from pathlib import Path

import requests

from .comfy_client import ComfyClient
from .episode_paths import resolve_episode_dir


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMFYUI_DIR = Path.home() / "HuellasStudioAI" / "ComfyUI"
MOTION_CONFIG = ROOT / "config" / "animation" / "episode_001_motion_prompts.json"
CHECKPOINT = "ltxv-2b-0.9.6-distilled-04-25.safetensors"
TEXT_ENCODER = "t5xxl_fp16.safetensors"
DISTILLED_SIGMAS = "1.0000, 0.9937, 0.9875, 0.9812, 0.9750, 0.9094, 0.7250, 0.4219, 0.0"
REQUIRED_NODES = {
    "CheckpointLoaderSimple",
    "CLIPLoader",
    "CLIPTextEncode",
    "LoadImage",
    "LTXVPreprocess",
    "LTXVImgToVideo",
    "LTXVConditioning",
    "StringToFloatList",
    "FloatToSigmas",
    "KSamplerSelect",
    "CFGGuider",
    "RandomNoise",
    "SamplerCustomAdvanced",
    "VAEDecode",
    "SaveImage",
}


def load_motion_config(path=MOTION_CONFIG):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    scenes = data.get("scenes")
    if not isinstance(scenes, dict) or not scenes:
        raise ValueError(f"Configuración de movimiento no válida: {path}")
    return data


def validate_animation_inputs(
    episode_dir,
    scene_id,
    comfyui_dir=DEFAULT_COMFYUI_DIR,
    width=512,
    height=288,
    frames=49,
):
    episode_dir = Path(episode_dir)
    comfyui_dir = Path(comfyui_dir).expanduser()
    if width < 256 or height < 144 or width % 32 or height % 32:
        raise ValueError("Ancho y alto deben ser múltiplos de 32 y tener al menos 256x144.")
    if frames < 9 or (frames - 1) % 8:
        raise ValueError("LTX requiere una cantidad de frames de 8n + 1 (por ejemplo, 49 o 97).")

    episode_path = episode_dir / "episode.json"
    if not episode_path.is_file():
        raise FileNotFoundError(episode_path)
    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    scene_ids = {scene.get("scene_id") for scene in episode.get("scenes", [])}
    if scene_id not in scene_ids:
        raise ValueError(f"Escena inexistente: {scene_id}")

    image_path = (
        episode_dir / "scenes" / scene_id / "composed"
        / f"{scene_id}_composed.png"
    )
    if not image_path.is_file():
        raise FileNotFoundError(
            f"Falta la imagen compuesta de {scene_id}: {image_path}"
        )

    checkpoint_path = (
        comfyui_dir / "models" / "checkpoints" / CHECKPOINT
    )
    text_encoder_path = (
        comfyui_dir / "models" / "text_encoders" / TEXT_ENCODER
    )
    missing = [
        path for path in (checkpoint_path, text_encoder_path)
        if not path.is_file() or path.stat().st_size < 1024
    ]
    if missing:
        raise FileNotFoundError(
            "Faltan modelos LTX. Ejecuta "
            "bash scripts/setup_ltx_animation_macos.sh. Archivos: "
            + ", ".join(str(path) for path in missing)
        )

    return {
        "episode": episode,
        "image_path": image_path,
        "checkpoint_path": checkpoint_path,
        "text_encoder_path": text_encoder_path,
    }


def check_ltx_comfyui(url="http://127.0.0.1:8188"):
    try:
        response = requests.get(f"{url.rstrip('/')}/object_info", timeout=30)
        response.raise_for_status()
        object_info = response.json()
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            f"No se pudo consultar ComfyUI en {url}. "
            "Inicia ComfyUI y vuelve a intentarlo."
        ) from exc

    missing = sorted(REQUIRED_NODES - set(object_info))
    if missing:
        raise RuntimeError(
            "La versión actual de ComfyUI no expone los nodos requeridos: "
            + ", ".join(missing)
            + ". Reinicia ComfyUI después de instalar los nodos Huellas LTX "
            "y comprueba que ComfyUI esté actualizado."
        )
    return object_info


def build_ltx_i2v_workflow(
    uploaded_image,
    positive_prompt,
    negative_prompt,
    seed,
    width=512,
    height=288,
    frames=49,
    fps=24,
    filename_prefix="huellas_motion/episode_001/SC003",
):
    if not uploaded_image or not isinstance(uploaded_image, str):
        raise ValueError("ComfyUI no devolvió el nombre de la imagen subida.")

    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": CHECKPOINT},
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": TEXT_ENCODER,
                "type": "ltxv",
                "device": "cpu",
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": positive_prompt, "clip": ["2", 0]},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["2", 0]},
        },
        "5": {
            "class_type": "LoadImage",
            "inputs": {"image": uploaded_image},
        },
        "6": {
            "class_type": "LTXVPreprocess",
            "inputs": {"image": ["5", 0], "img_compression": 38},
        },
        "7": {
            "class_type": "LTXVImgToVideo",
            "inputs": {
                "positive": ["3", 0],
                "negative": ["4", 0],
                "vae": ["1", 2],
                "image": ["6", 0],
                "width": width,
                "height": height,
                "length": frames,
                "batch_size": 1,
            },
        },
        "8": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["7", 0],
                "negative": ["7", 1],
                "frame_rate": float(fps),
            },
        },
        "9": {
            "class_type": "StringToFloatList",
            "inputs": {"string": DISTILLED_SIGMAS},
        },
        "10": {
            "class_type": "FloatToSigmas",
            "inputs": {"float_list": ["9", 0]},
        },
        "11": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "euler_ancestral"},
        },
        "12": {
            "class_type": "CFGGuider",
            "inputs": {
                "model": ["1", 0],
                "positive": ["8", 0],
                "negative": ["8", 1],
                "cfg": 1.0,
            },
        },
        "13": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": int(seed)},
        },
        "14": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["13", 0],
                "guider": ["12", 0],
                "sampler": ["11", 0],
                "sigmas": ["10", 0],
                "latent_image": ["7", 2],
            },
        },
        "15": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["14", 1], "vae": ["1", 2]},
        },
        "16": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["15", 0],
                "filename_prefix": filename_prefix,
            },
        },
    }


def _encode_frames(frames_dir, output_path, fps=24, width=1280, height=720, ffmpeg="ffmpeg"):
    ffmpeg_path = shutil.which(ffmpeg)
    if ffmpeg_path is None:
        raise FileNotFoundError(f"No se encontró FFmpeg ('{ffmpeg}') en PATH.")

    source_frames = sorted(
        Path(frames_dir).glob("*.png"),
        key=lambda path: path.name
    )
    if len(source_frames) < 9:
        raise RuntimeError(
            f"LTX devolvió solo {len(source_frames)} frames; se necesitan al menos 9."
        )

    numbered_dir = Path(frames_dir) / "sequence"
    numbered_dir.mkdir(parents=True, exist_ok=True)
    for index, source in enumerate(source_frames, 1):
        destination = numbered_dir / f"frame_{index:06d}.png"
        shutil.copy2(source, destination)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg_path, "-y",
        "-framerate", str(fps),
        "-start_number", "1",
        "-i", str(numbered_dir / "frame_%06d.png"),
        "-vf", (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
            "setsar=1,format=yuv420p"
        ),
        "-frames:v", str(len(source_frames)),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-movflags", "+faststart",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            "FFmpeg no pudo ensamblar el clip de movimiento:\n"
            + (result.stderr[-5000:] if result.stderr else "Sin detalles")
        )
    return output_path, len(source_frames)


def animate_scene(
    episode_id,
    scene_id,
    url="http://127.0.0.1:8188",
    comfyui_dir=DEFAULT_COMFYUI_DIR,
    width=512,
    height=288,
    frames=49,
    fps=24,
    seed=20261112,
    ffmpeg="ffmpeg",
    config_path=MOTION_CONFIG,
):
    episode_dir = resolve_episode_dir(episode_id, ROOT)
    inputs = validate_animation_inputs(
        episode_dir, scene_id, comfyui_dir, width, height, frames
    )
    config = load_motion_config(config_path)
    positive_prompt = config.get("scenes", {}).get(scene_id)
    if not positive_prompt:
        raise ValueError(f"No hay prompt de movimiento configurado para {scene_id}.")
    negative_prompt = config.get("negative_prompt", "")

    check_ltx_comfyui(url)
    client = ComfyClient(url)
    client.check()

    run_dir = (
        episode_dir / "motion_tests" / scene_id / f"seed_{int(seed)}"
    )
    frames_dir = run_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    if any(frames_dir.glob("*.png")):
        raise FileExistsError(
            f"Ya existen frames para esta semilla: {frames_dir}. "
            "Usa otra semilla para conservar la prueba anterior."
        )

    uploaded = client.upload_image(inputs["image_path"])
    workflow = build_ltx_i2v_workflow(
        uploaded_image=uploaded,
        positive_prompt=positive_prompt,
        negative_prompt=negative_prompt,
        seed=seed,
        width=width,
        height=height,
        frames=frames,
        fps=fps,
        filename_prefix=f"huellas_motion/{episode_id}/{scene_id}/{seed}",
    )

    print("\nHUELLAS STUDIO - LTX IMAGE TO VIDEO")
    print("=" * 52)
    print("Episodio:", episode_id)
    print("Escena:", scene_id)
    print("Modelo:", CHECKPOINT)
    print("Resolución:", f"{width}x{height}")
    print("Frames:", frames, f"({frames / fps:.2f}s a {fps} fps)")
    print("Seed:", seed)
    print("Prompt:", positive_prompt)

    prompt_id = client.submit(workflow)
    print("ComfyUI Prompt ID:", prompt_id)
    history = client.wait(prompt_id, timeout=3600)
    downloaded = client.download_images(history, frames_dir)
    if not downloaded:
        raise RuntimeError("LTX terminó sin devolver frames de imagen.")

    output_path = run_dir / f"{scene_id}_motion_test.mp4"
    output_path, frame_count = _encode_frames(
        frames_dir, output_path, fps=fps, ffmpeg=ffmpeg
    )

    manifest = {
        "episode_id": episode_id,
        "scene_id": scene_id,
        "model": CHECKPOINT,
        "text_encoder": TEXT_ENCODER,
        "seed": int(seed),
        "width": width,
        "height": height,
        "frames": frame_count,
        "fps": fps,
        "duration_seconds": round(frame_count / fps, 3),
        "source_image": str(inputs["image_path"]),
        "prompt_id": prompt_id,
        "prompt": positive_prompt,
        "negative_prompt": negative_prompt,
        "output": str(output_path),
    }
    (run_dir / "motion_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n[OK] CLIP DE MOVIMIENTO GENERADO")
    print("MP4:", output_path)
    print("Frames:", frame_count)
    return output_path
