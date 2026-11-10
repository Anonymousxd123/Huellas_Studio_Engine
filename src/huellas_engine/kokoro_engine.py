import json
import os
import platform
import re
import sys
from pathlib import Path

import numpy as np

SAMPLE_RATE = 24000
_PIPELINES = {}


def load_voice_profiles(path):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("provider") != "kokoro":
        raise ValueError("El proveedor TTS debe ser 'kokoro'")

    for language, profile in data.get("languages", {}).items():
        lang_code = profile.get("lang_code")
        narrator = profile.get("narrator", {})
        voice_id = narrator.get("voice_id", "")
        if not lang_code or not voice_id.startswith(lang_code):
            raise ValueError(
                f"Perfil de narrador inválido para {language}: "
                "lang_code y voice_id no coinciden"
            )
        for character, settings in profile.get("characters", {}).items():
            character_voice = settings.get("voice_id", "")
            if not character_voice.startswith(lang_code):
                raise ValueError(
                    f"Voz inválida para {language}/{character}: "
                    f"{character_voice}"
                )
    return data


def resolve_voice_settings(profiles, language, job):
    try:
        language_profile = profiles["languages"][language]
    except KeyError as exc:
        raise ValueError(
            f"No hay perfil Kokoro configurado para '{language}'"
        ) from exc

    if job.get("kind") == "narration":
        settings = language_profile["narrator"]
    else:
        character = job.get("character")
        try:
            settings = language_profile["characters"][character]
        except KeyError as exc:
            raise ValueError(
                f"No hay voz configurada para {language}/{character}"
            ) from exc

    voice_id = settings["voice_id"]
    if not voice_id.startswith(language_profile["lang_code"]):
        raise ValueError(
            f"La voz {voice_id} no corresponde al idioma {language}"
        )
    return {
        "lang_code": language_profile["lang_code"],
        "voice_id": voice_id,
        "speed": float(settings.get("speed", 1.0))
    }


def split_text_for_tts(text, max_chars=280):
    """Split long text at sentence/word boundaries before phonemization."""
    text = str(text).strip()
    if not text:
        return []

    sentences = re.split(r"(?<=[.!?¡¿…])\\s+", text)
    chunks = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= max_chars:
            chunks.append(sentence)
            continue

        current = ""
        for word in sentence.split():
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = word
            else:
                current = candidate
        if current:
            chunks.append(current)
    return chunks


def _select_device(device):
    if device == "mps" or (
        device == "auto"
        and sys.platform == "darwin"
        and platform.machine().lower() in ("arm64", "aarch64")
    ):
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "Falta PyTorch. Instala Huellas con el extra TTS: "
            "python -m pip install -e '.[tts]'"
        ) from exc

    if device != "auto":
        if device == "mps" and not torch.backends.mps.is_available():
            raise RuntimeError("MPS no está disponible en este Mac")
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA no está disponible")
        return device

    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _get_pipeline(lang_code, device="auto"):
    selected_device = _select_device(device)
    key = (lang_code, selected_device)
    if key not in _PIPELINES:
        try:
            from kokoro import KPipeline
        except ImportError as exc:
            raise RuntimeError(
                "Kokoro no está instalado. Ejecuta "
                "python -m pip install -e '.[tts]'"
            ) from exc
        _PIPELINES[key] = KPipeline(
            lang_code=lang_code,
            device=selected_device
        )
    return _PIPELINES[key], selected_device


def synthesize_text_to_file(
    text,
    output_path,
    lang_code,
    voice_id,
    speed=1.0,
    device="auto"
):
    try:
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError(
            "Falta SoundFile. Ejecuta python -m pip install -e '.[tts]'"
        ) from exc

    if not 0.5 <= float(speed) <= 1.5:
        raise ValueError("La velocidad Kokoro debe estar entre 0.5 y 1.5")
    if not voice_id.startswith(lang_code):
        raise ValueError(
            f"La voz {voice_id} no coincide con el idioma {lang_code}"
        )

    pipeline, selected_device = _get_pipeline(lang_code, device)
    chunks = []
    for text_chunk in split_text_for_tts(text):
        for result in pipeline(
            text_chunk,
            voice=voice_id,
            speed=float(speed)
        ):
            audio = getattr(result, "audio", None)
            if audio is None:
                continue
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            audio = np.asarray(audio, dtype=np.float32).squeeze()
            if audio.size:
                chunks.append(audio.reshape(-1))

    if not chunks:
        raise RuntimeError(f"Kokoro no generó audio para la voz {voice_id}")

    waveform = np.concatenate(chunks).astype(np.float32, copy=False)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(output_path.stem + ".tmp.wav")
    sf.write(temporary_path, waveform, SAMPLE_RATE, subtype="PCM_16")
    temporary_path.replace(output_path)

    return {
        "path": str(output_path),
        "duration_seconds": round(len(waveform) / SAMPLE_RATE, 3),
        "sample_rate": SAMPLE_RATE,
        "device": selected_device,
        "voice_id": voice_id
    }


def _mix_scene_audio(
    episode_dir,
    language,
    episode,
    manifest,
    line_gap_seconds=0.28
):
    try:
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError(
            "Falta SoundFile. Ejecuta python -m pip install -e '.[tts]'"
        ) from exc

    audio_root = Path(episode_dir) / "audio" / language
    timeline = []
    scene_buffers = []
    episode_cursor = 0.0
    jobs = manifest["jobs"]

    for scene in episode["scenes"]:
        scene_id = scene["scene_id"]
        scene_duration = float(scene["duration_seconds"])
        scene_frames = round(scene_duration * SAMPLE_RATE)
        buffer = np.zeros(scene_frames, dtype=np.float32)
        cursor = 0
        scene_jobs = sorted(
            (job for job in jobs if job["scene_id"] == scene_id),
            key=lambda job: job["sequence"]
        )

        for index, job in enumerate(scene_jobs):
            audio_path = Path(episode_dir) / job["output"]
            if not audio_path.is_file():
                raise FileNotFoundError(
                    f"Falta el audio de {job['job_id']}: {audio_path}"
                )
            samples, sample_rate = sf.read(
                audio_path, dtype="float32", always_2d=False
            )
            if sample_rate != SAMPLE_RATE:
                raise ValueError(
                    f"{audio_path} está a {sample_rate} Hz; "
                    f"se esperaba {SAMPLE_RATE} Hz"
                )
            if samples.ndim == 2:
                samples = samples.mean(axis=1)
            samples = np.asarray(samples, dtype=np.float32).reshape(-1)

            start_frame = cursor
            end_frame = start_frame + len(samples)
            if end_frame > scene_frames:
                used = end_frame / SAMPLE_RATE
                raise RuntimeError(
                    f"{scene_id}: el audio necesita {used:.2f}s, "
                    f"pero la escena dispone de {scene_duration:.2f}s. "
                    "Ajusta el guion, la velocidad o la duración; "
                    "no se recortará voz automáticamente."
                )

            buffer[start_frame:end_frame] += samples
            start_seconds = episode_cursor + start_frame / SAMPLE_RATE
            end_seconds = episode_cursor + end_frame / SAMPLE_RATE
            timeline.append({
                "job_id": job["job_id"],
                "scene_id": scene_id,
                "kind": job["kind"],
                "speaker_id": job["speaker_id"],
                "voice_id": job["voice_id"],
                "start": round(start_seconds, 3),
                "end": round(end_seconds, 3),
                "duration_seconds": round(len(samples) / SAMPLE_RATE, 3),
                "text": job["text"]
            })
            cursor = end_frame
            if index < len(scene_jobs) - 1:
                cursor += round(line_gap_seconds * SAMPLE_RATE)

        scene_buffers.append(buffer)
        episode_cursor += scene_duration

    final_mix = np.concatenate(scene_buffers) if scene_buffers else np.zeros(0)
    peak = float(np.max(np.abs(final_mix))) if final_mix.size else 0.0
    if peak > 0.98:
        final_mix *= 0.98 / peak

    mix_path = audio_root / "final_mix.wav"
    sf.write(mix_path, final_mix, SAMPLE_RATE, subtype="PCM_16")

    timeline_path = audio_root / "audio_timeline.json"
    timeline_path.write_text(
        json.dumps({
            "language": language,
            "sample_rate": SAMPLE_RATE,
            "duration_seconds": round(len(final_mix) / SAMPLE_RATE, 3),
            "cues": timeline
        }, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    return mix_path, timeline_path


def synthesize_episode_audio(
    episode_dir,
    language,
    profile_path,
    force=False,
    device="auto",
    line_gap_seconds=0.28
):
    from .audio_engine import build_voice_manifest

    episode_dir = Path(episode_dir)
    profiles = load_voice_profiles(profile_path)
    manifest_path, manifest = build_voice_manifest(episode_dir, language)
    episode = json.loads(
        (episode_dir / "episode.json").read_text(encoding="utf-8")
    )

    manifest["provider"] = "kokoro_local"
    manifest["model"] = profiles["model"]
    manifest["voice_selection"] = "configured_local_presets"
    manifest["reference_note"] = (
        "Preset voices selected as timbral alternatives to the project "
        "owner's Daniela (Spanish) and Akira (English) reference samples. "
        "No voice cloning is performed."
    )

    generated = 0
    reused = 0
    for job in manifest["jobs"]:
        settings = resolve_voice_settings(profiles, language, job)
        output_path = episode_dir / job["output"]
        job["voice_id"] = settings["voice_id"]
        job["speed"] = settings["speed"]

        if output_path.is_file() and not force:
            try:
                import soundfile as sf
                info = sf.info(output_path)
                job["audio_duration_seconds"] = round(
                    info.frames / info.samplerate, 3
                )
                job["status"] = "reused"
                reused += 1
                continue
            except (ImportError, RuntimeError, OSError):
                pass

        result = synthesize_text_to_file(
            text=job["text"],
            output_path=output_path,
            lang_code=settings["lang_code"],
            voice_id=settings["voice_id"],
            speed=settings["speed"],
            device=device
        )
        job["audio_duration_seconds"] = result["duration_seconds"]
        job["device"] = result["device"]
        job["status"] = "generated"
        generated += 1

    mix_path, timeline_path = _mix_scene_audio(
        episode_dir,
        language,
        episode,
        manifest,
        line_gap_seconds=line_gap_seconds
    )
    manifest["generated_jobs"] = generated
    manifest["reused_jobs"] = reused
    manifest["mix_path"] = str(mix_path)
    manifest["timeline_path"] = str(timeline_path)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    return {
        "manifest_path": manifest_path,
        "mix_path": mix_path,
        "timeline_path": timeline_path,
        "generated_jobs": generated,
        "reused_jobs": reused
    }
