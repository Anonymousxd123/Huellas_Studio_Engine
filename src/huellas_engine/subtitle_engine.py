import json
import textwrap
from pathlib import Path

from .localization_engine import load_episode_bundle


def format_srt_timestamp(seconds):
    milliseconds = max(0, round(float(seconds) * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return (
        f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},"
        f"{milliseconds:03d}"
    )


def split_subtitle_text(text, max_chars=42, max_lines=2):
    if max_chars < 1 or max_lines < 1:
        raise ValueError("Los límites de subtítulos deben ser positivos")

    words = str(text).split()
    if not words:
        return []

    lines = textwrap.wrap(
        " ".join(words),
        width=max_chars,
        break_long_words=True,
        break_on_hyphens=False
    )

    per_cue = []
    for index in range(0, len(lines), max_lines):
        per_cue.append("\n".join(lines[index:index + max_lines]))
    return per_cue


def build_subtitle_timeline(
    episode_dir,
    language,
    chars_per_second=15.0,
    max_chars=42,
    max_lines=2,
    cue_gap=0.12,
    scene_gap=0.0
):
    if chars_per_second <= 0:
        raise ValueError("chars_per_second debe ser mayor que cero")
    if cue_gap < 0 or scene_gap < 0:
        raise ValueError("Los espacios entre subtítulos no pueden ser negativos")

    bundle = load_episode_bundle(episode_dir, language)
    cues = []
    scene_start = 0.0
    cue_index = 1

    for scene in bundle["scenes"]:
        duration = float(scene["duration_seconds"])
        source_texts = []

        narration = scene.get("narration", "").strip()
        if narration:
            source_texts.append(narration)

        for line in scene.get("dialogue", []):
            text = line.get("text", "").strip()
            if text:
                source_texts.append(text)

        segments = []
        for source_text in source_texts:
            segments.extend(
                split_subtitle_text(source_text, max_chars, max_lines)
            )

        if segments:
            estimated = [
                max(1.0, len(segment.replace("\n", " ")) / chars_per_second)
                for segment in segments
            ]
            gaps = cue_gap * max(0, len(segments) - 1)
            available = max(0.1, duration - gaps)
            total_estimated = sum(estimated)
            scale = min(1.0, available / total_estimated)

            cursor = scene_start
            for segment, estimate in zip(segments, estimated):
                cue_duration = max(0.1, estimate * scale)
                end = min(scene_start + duration, cursor + cue_duration)
                if end <= cursor:
                    continue

                cues.append({
                    "index": cue_index,
                    "scene_id": scene["scene_id"],
                    "start": round(cursor, 3),
                    "end": round(end, 3),
                    "text": segment
                })
                cue_index += 1
                cursor = end + cue_gap

        scene_start += duration + scene_gap

    return {
        "episode_id": bundle["episode_id"],
        "language": language,
        "title": bundle["title"],
        "duration_seconds": round(max(0.0, scene_start - scene_gap), 3),
        "timing_basis": "estimated_from_text_length",
        "cues": cues
    }


def render_srt(timeline):
    blocks = []
    for cue in timeline["cues"]:
        blocks.append(
            f"{cue['index']}\n"
            f"{format_srt_timestamp(cue['start'])} --> "
            f"{format_srt_timestamp(cue['end'])}\n"
            f"{cue['text']}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def write_subtitles(episode_dir, languages=None, **options):
    episode_dir = Path(episode_dir)
    episode = json.loads(
        (episode_dir / "episode.json").read_text(encoding="utf-8")
    )
    languages = languages or episode.get("supported_languages", [])
    output_dir = episode_dir / "subtitles"
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs = []
    for language in languages:
        timeline = build_subtitle_timeline(
            episode_dir, language, **options
        )
        srt_path = output_dir / f"{language}.srt"
        json_path = output_dir / f"{language}_timeline.json"

        srt_path.write_text(
            render_srt(timeline),
            encoding="utf-8"
        )
        json_path.write_text(
            json.dumps(timeline, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        outputs.extend([srt_path, json_path])

    return outputs
