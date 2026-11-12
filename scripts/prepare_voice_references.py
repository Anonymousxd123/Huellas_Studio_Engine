#!/usr/bin/env python3
"""Create short, Whisper-aligned CosyVoice zero-shot voice references."""
import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "config" / "tts" / "production_profiles.json"


def _select_reference_window(result, max_seconds, min_seconds=4.0):
    """Choose a complete, contiguous speech span; never cut a phrase at a timer."""
    segments = [
        segment for segment in result.get("segments", [])
        if segment.get("text", "").strip()
        and float(segment.get("end", 0)) > float(segment.get("start", 0))
    ]
    candidates = []
    for start_index, first in enumerate(segments):
        start = float(first["start"])
        for end_index in range(start_index, len(segments)):
            last = segments[end_index]
            end = float(last["end"])
            if end - start > max_seconds:
                break
            if end_index > start_index:
                previous_end = float(segments[end_index - 1]["end"])
                if float(last["start"]) - previous_end > 1.25:
                    break
            duration = end - start
            if duration < min_seconds:
                continue
            text = " ".join(
                segment["text"].strip()
                for segment in segments[start_index:end_index + 1]
            )
            complete_sentence = text.rstrip().endswith((".", "!", "?", "…"))
            word_count = len(text.split())
            score = (
                -abs(duration - min(8.0, max_seconds - 0.2)) * 2.0
                + (5.0 if complete_sentence else 0.0)
                + min(word_count, 30) * 0.05
            )
            candidates.append({
                "start": start, "end": end, "text": text,
                "duration": duration, "score": score
            })
    if not candidates:
        raise RuntimeError(
            "Whisper no encontró una frase completa de entre "
            f"{min_seconds:.0f} y {max_seconds:.0f} segundos. "
            "Prueba con --max-seconds 12 o revisa el audio original."
        )
    return max(candidates, key=lambda candidate: candidate["score"])


def main():
    parser = argparse.ArgumentParser(
        description="Prepare short, transcript-aligned CosyVoice voice references"
    )
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    parser.add_argument("--languages", nargs="*", default=["es", "en"])
    parser.add_argument("--max-seconds", type=float, default=10.0)
    parser.add_argument("--whisper-model", default="small")
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
        selected = _select_reference_window(result, args.max_seconds)
        clip_start = max(0.0, selected["start"] - 0.08)
        clip_end = selected["end"] + 0.12
        if clip_end - clip_start > args.max_seconds:
            clip_end = clip_start + args.max_seconds
        duration = clip_end - clip_start
        if duration <= 0 or duration >= 30:
            raise RuntimeError(f"Duración de referencia inválida: {duration:.2f}s")

        transcript = selected["text"].strip()
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
            "language": language,
            "selected_start_seconds": round(selected["start"], 3),
            "selected_end_seconds": round(selected["end"], 3),
            "whisper_model": args.whisper_model
        }

        print(f"[OK] Referencia corta: {prepared_audio}")
        print(f"[OK] Fragmento: {selected['start']:.2f}s–{selected['end']:.2f}s")
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
