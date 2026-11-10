import json
from pathlib import Path

from .audio_engine import build_voice_manifest
from .elevenlabs_engine import synthesize_text_to_file as synthesize_elevenlabs
from .kokoro_engine import (
    _mix_scene_audio,
    load_voice_profiles,
    resolve_voice_settings,
    synthesize_text_to_file as synthesize_kokoro
)


def load_production_profile(path):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("provider") != "hybrid":
        raise ValueError("El proveedor de producción debe ser 'hybrid'")

    narration = data.get("narration", {})
    if narration.get("provider") != "elevenlabs":
        raise ValueError("La narración debe utilizar ElevenLabs")

    for language in ("es", "en"):
        voice_id = narration.get("voices", {}).get(language, {}).get("voice_id")
        if not voice_id:
            raise ValueError(
                f"Falta el Voice ID de ElevenLabs para {language}"
            )

    if data.get("dialogue", {}).get("provider") != "kokoro":
        raise ValueError("Los diálogos de personajes deben usar Kokoro")
    return data


def synthesize_episode_audio(
    episode_dir,
    language,
    profile_path,
    kokoro_profile_path,
    force=False,
    device="auto",
    line_gap_seconds=0.28
):
    episode_dir = Path(episode_dir)
    production = load_production_profile(profile_path)
    kokoro_profiles = load_voice_profiles(kokoro_profile_path)
    try:
        narrator = production["narration"]["voices"][language]
    except KeyError as exc:
        raise ValueError(f"No hay configuración TTS para {language}") from exc

    audio_root = episode_dir / "audio" / language
    manifest_path = audio_root / "voice_manifest.json"
    cache_path = audio_root / "tts_cache.json"
    previous_manifest = {}
    cache_source = cache_path if cache_path.is_file() else manifest_path
    if cache_source.is_file():
        try:
            previous_manifest = json.loads(
                cache_source.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            previous_manifest = {}
    previous_jobs = {
        job.get("job_id"): job
        for job in previous_manifest.get("jobs", [])
    }

    # Generate the new provider-neutral manifest only after reading the cache.
    manifest_path, manifest = build_voice_manifest(episode_dir, language)

    manifest["provider"] = "hybrid_elevenlabs_kokoro"
    manifest["voice_selection"] = "ElevenLabs narrator; Kokoro characters"
    manifest["models"] = {
        "narration": production["narration"]["model_id"],
        "dialogue": kokoro_profiles["model"]
    }

    generated = 0
    reused = 0
    for job in manifest["jobs"]:
        if job["kind"] == "narration":
            provider = "elevenlabs"
            voice_id = narrator["voice_id"]
            model_id = production["narration"]["model_id"]
            speed = None
            cache_signature = {
                "provider": provider,
                "voice_id": voice_id,
                "model_id": model_id,
                "text": job["text"]
            }
        else:
            provider = "kokoro"
            settings = resolve_voice_settings(
                kokoro_profiles, language, job
            )
            voice_id = settings["voice_id"]
            model_id = kokoro_profiles["model"]
            speed = settings["speed"]
            cache_signature = {
                "provider": provider,
                "voice_id": voice_id,
                "model_id": model_id,
                "speed": speed,
                "text": job["text"]
            }

        output_path = episode_dir / job["output"]
        job.update({
            "provider": provider,
            "voice_id": voice_id,
            "model_id": model_id
        })
        if speed is not None:
            job["speed"] = speed

        previous = previous_jobs.get(job["job_id"], {})
        cache_matches = all(
            previous.get(key) == value
            for key, value in cache_signature.items()
        )
        if output_path.is_file() and cache_matches and not force:
            try:
                import soundfile as sf
                info = sf.info(output_path)
                if info.samplerate == 24000 and info.frames > 0:
                    job["audio_duration_seconds"] = round(
                        info.frames / info.samplerate, 3
                    )
                    job["status"] = "reused"
                    reused += 1
                    continue
            except (ImportError, RuntimeError, OSError, ZeroDivisionError):
                pass

        if provider == "elevenlabs":
            result = synthesize_elevenlabs(
                text=job["text"],
                output_path=output_path,
                voice_id=voice_id,
                model_id=model_id
            )
        else:
            result = synthesize_kokoro(
                text=job["text"],
                output_path=output_path,
                lang_code=settings["lang_code"],
                voice_id=voice_id,
                speed=speed,
                device=device
            )

        job["audio_duration_seconds"] = result["duration_seconds"]
        job["status"] = "generated"
        job["device"] = result.get("device", "cloud_api")
        generated += 1

    mix_path, timeline_path = _mix_scene_audio(
        episode_dir,
        language,
        json.loads(
            (episode_dir / "episode.json").read_text(encoding="utf-8")
        ),
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
    cache_path.write_text(
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
