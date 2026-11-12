#!/usr/bin/env python3
"""Create short, Whisper-aligned CosyVoice zero-shot voice references."""
import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "config" / "tts" / "production_profiles.json"


def _transcript_words(result, max_seconds):
    words = []
    for segment in result.get("segments", []):
        for word in segment.get("words", []):
            start = float(word.get("start", 0))
            end = float(word.get("end", 0))
            text = word.get("word", "")
            if text.strip() and end > start and end <= max_seconds:
                words.append({"start": start, "end": end, "text": text})
    return words


def main():
    parser = argparse.ArgumentParser(
        description="Prepare short, transcript-aligned CosyVoice voice references"
    )
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    parser.add_argument("--languages", nargs="*", default=["es", "en"])
    parser.add_argument("--max-seconds", type=float, default=10.0)
    parser.add_argument("--whisper-model", default="tiny")
    args = parser.parse_args()

    if not 3 <= args.max_seconds < 30:
        raise ValueError("--max-seconds debe estar entre 3 y menos de 30")

    profile = json.loads(
        Path(args.profile).expanduser().read_text(encoding="utf-8")
    )
    voices = profile["narration"]["voices"]

    import whisper

    print(f"[WHISPER] Cargando modelo {args.whisper_model} en CPU...")
    model = whisper.load_model(args.whisper_model, device="cpu")
    prepared_dir = None
    manifest = {"version": 1, "voices": {}}

    for language in args.languages:
        if language not in voices:
            raise ValueError(f"Idioma no configurado: {language}")
        voice = voices[language]
        source = Path(voice["reference_audio"]).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(source)

        language_name = "English" if language == "en" else "Spanish"
        print(f"\n========== {voice['name']} ({language_name}) ==========")
        print(f"Referencia original: {source}")

        result = model.transcribe(
            str(source),
            language=language,
            task="transcribe",
            word_timestamps=True,
            fp16=False,
            verbose=False,
            condition_on_previous_text=False
        )
        words = _transcript_words(result, args.max_seconds)
        if not words:
            raise RuntimeError(
                f"Whisper no encontró palabras completas en los primeros "
                f"{args.max_seconds}s de {source}. Revisa el audio original."
            )

        clip_start = max(0.0, words[0]["start"] - 0.10)
        clip_end = min(args.max_seconds, words[-1]["end"] + 0.15)
        duration = clip_end - clip_start
        if duration <= 0 or duration >= 30:
            raise RuntimeError(f"Duración de referencia inválida: {duration:.2f}s")

        transcript = "".join(word["text"] for word in words).strip()
        if len(transcript.split()) < 5:
            raise RuntimeError(
                f"Referencia demasiado corta para {voice['name']}: {transcript}"
            )

        prepared_dir = source.parent / "cosyvoice_prepared"
        prepared_dir.mkdir(parents=True, exist_ok=True)
        prepared_audio = prepared_dir / f"{voice['name'].lower()}_reference.wav"
        command = [
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{clip_start:.3f}",
            "-i", str(source),
            "-t", f"{duration:.3f}",
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(prepared_audio)
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)

        manifest["voices"][language] = {
            "source_audio": str(source),
            "source_mtime_ns": source.stat().st_mtime_ns,
            "prepared_audio": str(prepared_audio),
            "reference_text": transcript,
            "duration_seconds": round(duration, 3),
            "language": language
        }

        print(f"[OK] Referencia corta: {prepared_audio}")
        print(f"[OK] Duración: {duration:.2f}s")
        print(f"[OK] Transcripción alineada: {transcript}")

    if prepared_dir is None:
        raise RuntimeError("No se preparó ninguna referencia")
    manifest_path = prepared_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n[OK] Manifiesto guardado: {manifest_path}")
    print("REFERENCIAS COSYVOICE PREPARADAS")


if __name__ == "__main__":
    main()
