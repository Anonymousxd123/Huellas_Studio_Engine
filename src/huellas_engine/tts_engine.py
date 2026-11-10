import json
from pathlib import Path

from .audio_engine import build_voice_manifest
from .cosyvoice_engine import (
    load_cosyvoice_profile,
    synthesize_narration_batch
)
from .kokoro_engine import (
    _mix_scene_audio,
    load_voice_profiles,
    resolve_voice_settings,
    synthesize_text_to_file as synthesize_kokoro
)


def load_production_profile(path):
    return load_cosyvoice_profile(path)


def synthesize_episode_audio(
    episode_dir,
    language,
    profile_path,
    kokoro_profile_path=None,
    force=False,
    device="auto",
    line_gap_seconds=0.28
):
    episode_dir = Path(episode_dir).resolve()
    production = load_production_profile(profile_path)
    root = Path(__file__).resolve().parents[2]
    if kokoro_profile_path is None:
        kokoro_profile_path = (
            root / production["dialogue"]["profile"]
        )
    kokoro_profiles = load_voice_profiles(kokoro_profile_path)

    if language not in production["narration"]["voices"]:
        raise ValueError(f"No hay narrador configurado para {language}")

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

    manifest_path, manifest = build_voice_manifest(episode_dir, language)
    voice = production["narration"]["voices"][language]
    narration_model = production["narration"]["model_id"]
    manifest["provider"] = "local_cosyvoice_kokoro"
    manifest["voice_selection"] = (
        "CosyVoice 3 local narrator cloning; Kokoro local character dialogue"
    )
    manifest["models"] = {
        "narration": narration_model,
        "dialogue": kokoro_profiles["model"]
    }

    generated = 0
    reused = 0
    pending_narration = []

    for job in manifest["jobs"]:
        output_path = episode_dir / job["output"]
        previous = previous_jobs.get(job["job_id"], {})

        if job["kind"] == "narration":
            provider = "cosyvoice3_mps"
            voice_id = f"{voice['name'].lower()}_reference_clone"
            cache_signature = {
                "provider": provider,
                "voice_id": voice_id,
                "model_id": narration_model,
                "reference_audio": voice["reference_audio"],
                "reference_text": voice["reference_text"],
                "text": job["text"]
            }
            job.update({
                "provider": provider,
                "voice_id": voice_id,
                "model_id": narration_model
            })
            reference = Path(voice["reference_audio"]).expanduser()
            if reference.is_file():
                cache_signature["reference_size"] = reference.stat().st_size
                cache_signature["reference_mtime_ns"] = reference.stat().st_mtime_ns
                job["reference_audio"] = str(reference.resolve())
            else:
                job["reference_audio"] = str(reference)

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
                        job.update(cache_signature)
                        reused += 1
                        continue
                except (ImportError, RuntimeError, OSError, ZeroDivisionError):
                    pass
            pending_narration.append(job)
            job["_cache_signature"] = cache_signature
            continue

        settings = resolve_voice_settings(
            kokoro_profiles, language, job
        )
        provider = "kokoro"
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
        job.update({
            "provider": provider,
            "voice_id": voice_id,
            "model_id": model_id,
            "speed": speed
        })

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
                    job["device"] = previous.get("device", "cached")
                    job["status"] = "reused"
                    reused += 1
                    continue
            except (ImportError, RuntimeError, OSError, ZeroDivisionError):
                pass

        result = synthesize_kokoro(
            text=job["text"],
            output_path=output_path,
            lang_code=settings["lang_code"],
            voice_id=voice_id,
            speed=speed,
            device=device
        )
        job["audio_duration_seconds"] = result["duration_seconds"]
        job["device"] = result["device"]
        job["status"] = "generated"
        generated += 1

    if pending_narration:
        result_map = synthesize_narration_batch(
            jobs=pending_narration,
            language=language,
            profile=production,
            work_dir=audio_root,
            episode_dir=episode_dir,
            root=root
        )
        for job in pending_narration:
            result = result_map.get(job["job_id"])
            if result is None:
                raise RuntimeError(
                    f"CosyVoice no devolvió resultado para {job['job_id']}"
                )
            job["audio_duration_seconds"] = result["duration_seconds"]
            job["device"] = result["device"]
            job["status"] = "generated"
            job.update(job.pop("_cache_signature"))
            generated += 1

    for job in manifest["jobs"]:
        job.pop("_cache_signature", None)

    episode = json.loads(
        (episode_dir / "episode.json").read_text(encoding="utf-8")
    )
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
