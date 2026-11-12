import json
from pathlib import Path

from .localization_engine import load_episode_bundle


def build_voice_manifest(
    episode_dir,
    language,
    narrator_speaker="narrator",
    character_speakers=None,
    words_per_minute=150
):
    """Create provider-neutral TTS jobs without selecting a voice vendor."""
    if words_per_minute <= 0:
        raise ValueError("words_per_minute debe ser mayor que cero")

    character_speakers = character_speakers or {
        "dog": "dog",
        "cat": "cat"
    }
    episode_dir = Path(episode_dir)
    bundle = load_episode_bundle(episode_dir, language)

    jobs = []
    sequence = 1
    for scene in bundle["scenes"]:
        scene_id = scene["scene_id"]
        narration = scene.get("narration", "").strip()
        if narration:
            jobs.append({
                "job_id": f"{scene_id}_narration",
                "sequence": sequence,
                "scene_id": scene_id,
                "kind": "narration",
                "speaker_id": narrator_speaker,
                "language": language,
                "text": narration,
                "estimated_duration_seconds": round(
                    len(narration.split()) * 60 / words_per_minute, 2
                ),
                "output": (
                    f"audio/{language}/{scene_id}/"
                    f"{scene_id}_narration.wav"
                ),
                "status": "pending"
            })
            sequence += 1

        for line_index, line in enumerate(scene.get("dialogue", []), 1):
            text = line.get("text", "").strip()
            if not text:
                continue
            character = line["character"]
            speaker_id = character_speakers.get(character, character)
            jobs.append({
                "job_id": f"{scene_id}_dialogue_{line_index:02d}",
                "sequence": sequence,
                "scene_id": scene_id,
                "kind": "dialogue",
                "character": character,
                "speaker_id": speaker_id,
                "language": language,
                "text": text,
                "estimated_duration_seconds": round(
                    len(text.split()) * 60 / words_per_minute, 2
                ),
                "output": (
                    f"audio/{language}/{scene_id}/"
                    f"{scene_id}_dialogue_{line_index:02d}.wav"
                ),
                "status": "pending"
            })
            sequence += 1

    manifest = {
        "episode_id": bundle["episode_id"],
        "episode_title": bundle["title"],
        "language": language,
        "provider": None,
        "voice_selection": "pending_business_decision",
        "words_per_minute": words_per_minute,
        "total_jobs": len(jobs),
        "speakers": {
            "narrator": narrator_speaker,
            "characters": character_speakers
        },
        "jobs": jobs
    }

    output_dir = episode_dir / "audio" / language
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "voice_manifest.json"
    output_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    return output_path, manifest
