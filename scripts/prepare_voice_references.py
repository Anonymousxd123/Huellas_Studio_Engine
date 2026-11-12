#!/usr/bin/env python3
"""Prepare full-length, transcript-verified CosyVoice voice references.

Uses the original ElevenLabs WAVs already configured in production_profiles.json.
No ASR model or network download is needed: reference_text is the reviewed,
exact transcript associated with the selected clip.
"""
import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "config" / "tts" / "production_profiles.json"


def _probe_audio(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=sample_rate,channels,duration",
            "-of", "json", str(path)
        ],
        check=True,
        capture_output=True,
        text=True
    )
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise ValueError(f"No se encontró una pista de audio en {path}")
    stream = streams[0]
    return {
        "sample_rate": int(stream["sample_rate"]),
        "channels": int(stream["channels"]),
        "duration_seconds": float(stream.get("duration") or 0)
    }


def _prepare_voice(language, voice):
    source = Path(voice["reference_audio"]).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Falta la referencia de {voice['name']}: {source}")

    transcript = voice.get("reference_text", "").strip()
    if not transcript:
        raise ValueError(f"Falta la transcripción revisada de {voice['name']}")

    duration = float(voice.get("reference_duration_seconds", 0))
    if not 0 < duration < 30:
        raise ValueError(
            f"{voice['name']}: reference_duration_seconds debe ser mayor que 0 "
            "y menor que 30."
        )

    source_info = _probe_audio(source)
    if source_info["duration_seconds"] < duration:
        raise ValueError(
            f"{voice['name']}: el recorte solicitado ({duration:.2f}s) "
            f"supera la duración del original ({source_info['duration_seconds']:.2f}s)."
        )

    prepared_dir = source.parent / "cosyvoice_prepared"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    prepared = prepared_dir / f"{voice['name'].lower()}_reference.wav"

    manifest_path = prepared_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
            cached = previous.get("voices", {}).get(language, {})
            cached_audio = Path(cached.get("prepared_audio", "")).expanduser()
            cache_matches = (
                cached.get("source_audio") == str(source)
                and cached.get("source_mtime_ns") == source.stat().st_mtime_ns
                and cached.get("source_size_bytes") == source.stat().st_size
                and cached.get("reference_text") == transcript
                and abs(float(cached.get("duration_seconds", 0)) - duration) <= 0.05
                and cached_audio.is_file()
            )
            if cache_matches:
                cached_info = _probe_audio(cached_audio)
                cache_matches = (
                    cached_info["sample_rate"] == 16000
                    and cached_info["channels"] == 1
                    and abs(cached_info["duration_seconds"] - duration) <= 0.05
                )
            if cache_matches:
                print(
                    f"[OK] {voice['name']}: referencia preparada vigente; "
                    "se reutiliza."
                )
                return prepared_dir, cached
        except (OSError, ValueError, TypeError, json.JSONDecodeError, subprocess.CalledProcessError):
            pass

    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(source),
            "-t", f"{duration:.3f}",
            "-map", "0:a:0",
            "-vn",
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(prepared)
        ],
        check=True,
        capture_output=True,
        text=True
    )

    prepared_info = _probe_audio(prepared)
    if prepared_info["sample_rate"] != 16000 or prepared_info["channels"] != 1:
        raise RuntimeError(
            f"{voice['name']}: la referencia preparada no quedó en mono/16 kHz."
        )
    if not 0 < prepared_info["duration_seconds"] < 30:
        raise RuntimeError(
            f"{voice['name']}: duración preparada inválida "
            f"({prepared_info['duration_seconds']:.2f}s)."
        )

    entry = {
        "source_audio": str(source),
        "source_mtime_ns": source.stat().st_mtime_ns,
        "source_size_bytes": source.stat().st_size,
        "prepared_audio": str(prepared),
        "reference_text": transcript,
        "duration_seconds": round(prepared_info["duration_seconds"], 3),
        "language": language,
        "selected_start_seconds": 0.0,
        "selected_end_seconds": round(prepared_info["duration_seconds"], 3),
        "transcript_source": "reviewed production_profiles.json",
        "source_sample_rate": source_info["sample_rate"],
        "source_channels": source_info["channels"]
    }

    print(f"[OK] {voice['name']}: {prepared_info['duration_seconds']:.2f}s")
    print(f"[OK] Original: {source_info['duration_seconds']:.2f}s")
    print(f"[OK] Formato preparado: mono / 16000 Hz")
    print(f"[OK] Texto asociado: {transcript}")
    return prepared_dir, entry


def main():
    parser = argparse.ArgumentParser(
        description="Prepare reviewed, long CosyVoice reference clips without ASR."
    )
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    parser.add_argument("--languages", nargs="*", default=["es", "en"])
    args = parser.parse_args()

    profile = json.loads(
        Path(args.profile).expanduser().read_text(encoding="utf-8")
    )
    voices = profile["narration"]["voices"]

    manifest_by_dir = {}
    for language in args.languages:
        if language not in voices:
            raise ValueError(f"Idioma no configurado: {language}")
        voice = voices[language]
        print(f"\n========== {voice['name']} ({language}) ==========")
        prepared_dir, entry = _prepare_voice(language, voice)
        if prepared_dir not in manifest_by_dir:
            manifest_path = prepared_dir / "manifest.json"
            try:
                existing = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                ) if manifest_path.is_file() else {}
            except (OSError, json.JSONDecodeError):
                existing = {}
            if not isinstance(existing.get("voices"), dict):
                existing = {}
            manifest_by_dir[prepared_dir] = {
                "version": 2,
                "voices": existing.get("voices", {})
            }
        manifest_by_dir[prepared_dir]["voices"][language] = entry

    for directory, manifest in manifest_by_dir.items():
        manifest_path = directory / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8"
        )
        print(f"\n[OK] Manifiesto: {manifest_path}")

    print("\nREFERENCIAS LARGAS Y TRANSCRIPCIONES REVISADAS PREPARADAS")


if __name__ == "__main__":
    main()
