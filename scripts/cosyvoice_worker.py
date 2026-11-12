#!/usr/bin/env python3
"""One-shot CosyVoice MPS worker. Loads the model once for a batch of jobs."""
import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-dir", required=True)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--response", required=True)
    parser.add_argument("--fp16", action="store_true")
    args = parser.parse_args()

    engine_dir = Path(args.engine_dir).expanduser().resolve()
    model_dir = Path(args.model_dir).expanduser().resolve()
    sys.path.insert(0, str(engine_dir))
    sys.path.insert(0, str(engine_dir / "third_party" / "Matcha-TTS"))
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    request_path = Path(args.request)
    response_path = Path(args.response)
    payload = json.loads(request_path.read_text(encoding="utf-8"))

    print(f"[COSYVOICE WORKER] Python: {sys.executable}", flush=True)

    import torch
    import torchaudio
    from cosyvoice.cli.cosyvoice import AutoModel

    print(
        f"[COSYVOICE WORKER] PyTorch: {torch.__version__} | "
        f"TorchAudio: {torchaudio.__version__} | "
        f"MPS: {torch.backends.mps.is_available()}",
        flush=True
    )

    if not torch.backends.mps.is_available():
        raise RuntimeError(
            "PyTorch MPS no está disponible. Comprueba la instalación "
            "de PyTorch en el entorno de CosyVoice."
        )

    results = []
    for job in payload["jobs"]:
        reference = Path(job["reference_audio"]).expanduser().resolve()
        if not reference.is_file():
            raise FileNotFoundError(f"Falta referencia vocal: {reference}")
        if not job.get("reference_text", "").strip():
            raise ValueError(
                f"Falta la transcripción exacta de la referencia: {job['job_id']}"
            )
        audio_info = torchaudio.info(str(reference))
        reference_duration = audio_info.num_frames / audio_info.sample_rate
        if reference_duration > 30:
            raise ValueError(
                f"La referencia de {job['job_id']} dura "
                f"{reference_duration:.2f}s; CosyVoice admite máximo 30s. "
                "Ejecuta scripts/prepare_voice_references.py para crear "
                "referencias cortas alineadas con Whisper."
            )

    # Load the model only after every reference passes preflight.
    model = AutoModel(model_dir=str(model_dir), fp16=args.fp16)

    for job in payload["jobs"]:
        reference = Path(job["reference_audio"]).expanduser().resolve()
        output = Path(job["output_path"]).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        mode = job.get("mode", "zero_shot")
        speed = float(job.get("speed", 1.0))
        if not 0.8 <= speed <= 1.2:
            raise ValueError(f"Velocidad fuera del rango seguro: {speed}")

        if mode == "zero_shot":
            prompt_text = (
                "You are a helpful assistant.<|endofprompt|>"
                + job["reference_text"].strip()
            )
            inference = model.inference_zero_shot(
                job["text"], prompt_text, str(reference),
                stream=False, speed=speed
            )
        elif mode == "instruct2":
            instruction = job.get("instruct_text", "").strip()
            if not instruction:
                raise ValueError(
                    f"Falta instruct_text para {job['job_id']}"
                )
            inference = model.inference_instruct2(
                job["text"], instruction + "<|endofprompt|>",
                str(reference), stream=False, speed=speed
            )
        else:
            raise ValueError(f"Modo CosyVoice no soportado: {mode}")

        chunks = []
        for item in inference:
            speech = item.get("tts_speech")
            if speech is not None and speech.numel():
                chunks.append(speech)

        if not chunks:
            raise RuntimeError(
                f"CosyVoice no generó audio para {job['job_id']}"
            )

        waveform = torch.cat(chunks, dim=1).cpu()
        temporary = output.with_name(output.stem + ".tmp.wav")
        torchaudio.save(str(temporary), waveform, model.sample_rate)
        temporary.replace(output)

        results.append({
            "job_id": job["job_id"],
            "output_path": str(output),
            "duration_seconds": round(
                waveform.shape[1] / model.sample_rate, 3
            ),
            "sample_rate": model.sample_rate,
            "device": str(model.model.device)
        })

    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(
        json.dumps({"results": results}, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
