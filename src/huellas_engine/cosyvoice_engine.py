import json
import subprocess
import tempfile
from pathlib import Path


MODEL_ID = "FunAudioLLM/Fun-CosyVoice3-0.5B-2512"


def _project_root():
    return Path(__file__).resolve().parents[2]


def _resolve_path(value, root=None):
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (root or _project_root()) / path
    return path.resolve()


def load_cosyvoice_profile(path):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("provider") != "local_hybrid":
        raise ValueError("El proveedor TTS debe ser 'local_hybrid'")

    narration = data.get("narration", {})
    if narration.get("provider") != "cosyvoice3_mps":
        raise ValueError("La narración debe utilizar CosyVoice 3 local")

    voices = narration.get("voices", {})
    for language in ("es", "en"):
        voice = voices.get(language, {})
        if not voice.get("reference_audio"):
            raise ValueError(
                f"Falta reference_audio para la voz narradora {language}"
            )
        if "reference_text" not in voice:
            raise ValueError(
                f"Falta reference_text para la voz narradora {language}"
            )

    if data.get("dialogue", {}).get("provider") != "kokoro":
        raise ValueError("Los diálogos locales deben usar Kokoro")
    return data


def resolve_cosyvoice_runtime(profile, root=None):
    root = root or _project_root()
    narration = profile["narration"]
    engine_dir = _resolve_path(narration["engine_dir"], root)
    model_dir = _resolve_path(narration["model_dir"], root)
    python_path = _resolve_path(
        narration.get("python", str(Path(narration["engine_dir"]) / ".venv/bin/python")),
        root
    )
    worker = root / "scripts" / "cosyvoice_worker.py"

    missing = [
        str(path) for path in (engine_dir, model_dir, python_path, worker)
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError(
            "Falta la instalación local de CosyVoice. Elementos ausentes: "
            + ", ".join(missing)
            + ". Ejecuta bash scripts/setup_cosyvoice_mps_macos.sh"
        )
    return {
        "engine_dir": engine_dir,
        "model_dir": model_dir,
        "python": python_path,
        "worker": worker,
        "fp16": bool(narration.get("fp16", False))
    }


def _verify_cosyvoice_python(python_path):
    """Verify the exact interpreter that will launch the worker."""
    check = (
        "import sys, torch, torchaudio; "
        "print('PYTHON=' + sys.executable); "
        "print('TORCH=' + torch.__version__); "
        "print('TORCHAUDIO=' + torchaudio.__version__); "
        "print('MPS=' + str(torch.backends.mps.is_available()))"
    )
    result = subprocess.run(
        [str(python_path), "-c", check],
        capture_output=True,
        text=True
    )
    output = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )
    if result.returncode != 0:
        raise RuntimeError(
            "El Python configurado para CosyVoice no puede importar "
            "PyTorch/TorchAudio.\n"
            f"Intérprete: {python_path}\n"
            f"Diagnóstico:\n{output}"
        )
    if "MPS=True" not in result.stdout:
        raise RuntimeError(
            "El Python configurado para CosyVoice importa PyTorch, "
            "pero MPS no está disponible.\n"
            f"Intérprete: {python_path}\n"
            f"Diagnóstico:\n{output}"
        )
    return result.stdout.strip()


def _prepare_reference(reference, destination):
    reference = Path(reference).expanduser().resolve()
    if not reference.is_file():
        raise FileNotFoundError(
            f"No existe el audio de referencia de voz: {reference}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(reference),
        "-ar", "16000", "-ac", "1",
        str(destination)
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "FFmpeg no está instalado. Ejecuta: brew install ffmpeg"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"No se pudo convertir la referencia vocal: {exc.stderr[-1500:]}"
        ) from exc
    return destination


def synthesize_narration_batch(
    jobs,
    language,
    profile,
    work_dir,
    episode_dir,
    root=None
):
    if not jobs:
        return {}

    root = root or _project_root()
    voice = profile["narration"]["voices"][language]
    runtime = resolve_cosyvoice_runtime(profile, root)
    work_dir = Path(work_dir)
    episode_dir = Path(episode_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    reference = _resolve_path(voice["reference_audio"], root)
    if not reference.is_file():
        raise FileNotFoundError(
            f"No existe el audio de referencia de {voice.get('name', language)}: "
            f"{reference}"
        )

    reference_text = voice.get("reference_text", "").strip()
    if not reference_text or "REPLACE_WITH" in reference_text:
        raise ValueError(
            f"Configura la transcripción exacta de la referencia de "
            f"{voice.get('name', language)} en "
            "config/tts/production_profiles.json"
        )

    prepared_reference = work_dir / "references" / f"{language}_reference_16k.wav"
    if (
        not prepared_reference.is_file()
        or prepared_reference.stat().st_mtime < reference.stat().st_mtime
    ):
        _prepare_reference(reference, prepared_reference)

    payload_jobs = []
    for job in jobs:
        payload_jobs.append({
            "job_id": job["job_id"],
            "text": job["text"],
            "reference_audio": str(prepared_reference),
            "reference_text": reference_text,
            "output_path": str((episode_dir / job["output"]).resolve())
        })

    with tempfile.TemporaryDirectory(prefix="huellas-cosyvoice-") as temp:
        temp_dir = Path(temp)
        request_path = temp_dir / "request.json"
        response_path = temp_dir / "response.json"
        request_path.write_text(
            json.dumps({"jobs": payload_jobs}, ensure_ascii=False),
            encoding="utf-8"
        )
        runtime_check = _verify_cosyvoice_python(runtime["python"])
        print("[COSYVOICE PREFLIGHT] " + runtime_check.replace("\n", " | "))

        command = [
            str(runtime["python"]),
            str(runtime["worker"]),
            "--engine-dir", str(runtime["engine_dir"]),
            "--model-dir", str(runtime["model_dir"]),
            "--request", str(request_path),
            "--response", str(response_path)
        ]
        if runtime["fp16"]:
            command.append("--fp16")

        try:
            completed = subprocess.run(
                command,
                cwd=runtime["engine_dir"],
                capture_output=True,
                text=True,
                timeout=7200
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                "CosyVoice superó el límite de 2 horas para el lote de voz."
            ) from exc

        if completed.returncode != 0:
            details = "\n".join(
                part for part in (completed.stdout, completed.stderr) if part
            )[-8000:]
            raise RuntimeError(
                "Falló CosyVoice MPS.\n"
                f"Python utilizado: {runtime['python']}\n"
                "Detalle del proceso:\n" + details
            )
        if not response_path.is_file():
            raise RuntimeError(
                "CosyVoice terminó sin producir el archivo de resultados."
            )
        result_data = json.loads(response_path.read_text(encoding="utf-8"))

    return {
        item["job_id"]: item
        for item in result_data.get("results", [])
    }
