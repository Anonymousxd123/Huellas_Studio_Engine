"""Script pacing checks performed before expensive TTS and rendering steps."""
import json
import re
from pathlib import Path

from .localization_engine import load_episode_bundle


_WORD_PATTERN = re.compile(r"\\b[\\w]+(?:['’][\\w]+)*\\b", re.UNICODE)


def count_spoken_words(text):
    """Count spoken tokens consistently across Spanish and English."""
    return len(_WORD_PATTERN.findall(str(text or "")))


def analyze_episode_pacing(
    episode_dir,
    languages=None,
    words_per_minute=128.0,
    line_gap_seconds=0.28,
    min_scene_utilization=0.75,
    max_scene_utilization=0.995,
    min_episode_coverage=0.85,
):
    """Estimate voice occupancy and reject underwritten or overfilled scenes.

    The estimate includes the configured gaps between narration/dialogue clips.
    Actual generated clip durations are still checked by the audio mixer.
    """
    if words_per_minute <= 0:
        raise ValueError("words_per_minute debe ser mayor que cero")
    if line_gap_seconds < 0:
        raise ValueError("line_gap_seconds no puede ser negativo")
    if not 0 <= min_scene_utilization < max_scene_utilization <= 1:
        raise ValueError("Los límites de ocupación por escena no son válidos")
    if not 0 < min_episode_coverage <= 1:
        raise ValueError("min_episode_coverage debe estar entre 0 y 1")

    episode_dir = Path(episode_dir)
    episode = json.loads(
        (episode_dir / "episode.json").read_text(encoding="utf-8")
    )
    source_scenes = episode.get("scenes", [])
    if not source_scenes:
        raise ValueError("El episodio no contiene escenas")

    planned_duration = sum(
        float(scene.get("duration_seconds", 0))
        for scene in source_scenes
    )
    target_duration = float(
        episode.get("target_duration_seconds") or planned_duration
    )
    errors = []

    if target_duration <= 0:
        raise ValueError("target_duration_seconds debe ser mayor que cero")
    if abs(planned_duration - target_duration) > 1.0:
        errors.append(
            "La suma de las escenas "
            f"({planned_duration:.1f}s) no coincide con el objetivo "
            f"({target_duration:.1f}s)."
        )

    selected_languages = languages or episode.get("supported_languages", [])
    reports = {}

    for language in selected_languages:
        bundle = load_episode_bundle(episode_dir, language)
        scene_reports = []
        total_words = 0
        total_estimated_seconds = 0.0

        for scene in bundle["scenes"]:
            scene_id = scene["scene_id"]
            duration = float(scene["duration_seconds"])
            narration = str(scene.get("narration", "")).strip()
            dialogue = [
                str(line.get("text", "")).strip()
                for line in scene.get("dialogue", [])
                if str(line.get("text", "")).strip()
            ]
            narration_words = count_spoken_words(narration)
            dialogue_words = sum(count_spoken_words(line) for line in dialogue)
            word_count = narration_words + dialogue_words
            job_count = int(bool(narration)) + len(dialogue)
            gaps = max(0, job_count - 1) * line_gap_seconds
            speech_seconds = word_count * 60.0 / words_per_minute
            estimated_seconds = speech_seconds + gaps
            utilization = estimated_seconds / duration if duration > 0 else 0.0

            scene_reports.append({
                "scene_id": scene_id,
                "duration_seconds": duration,
                "narration_words": narration_words,
                "dialogue_words": dialogue_words,
                "total_words": word_count,
                "estimated_voice_seconds": round(estimated_seconds, 2),
                "utilization": round(utilization, 4),
            })
            total_words += word_count
            total_estimated_seconds += estimated_seconds

            if duration <= 0:
                errors.append(f"{language}/{scene_id}: duración de escena inválida.")
            elif utilization < min_scene_utilization:
                errors.append(
                    f"{language}/{scene_id}: voz estimada en "
                    f"{utilization:.0%} de la escena; mínimo "
                    f"{min_scene_utilization:.0%}. Amplía el guion o ajusta "
                    "la duración visual."
                )
            elif utilization > max_scene_utilization:
                errors.append(
                    f"{language}/{scene_id}: voz estimada en "
                    f"{utilization:.1%} de la escena; máximo "
                    f"{max_scene_utilization:.1%}. Reduce el texto o aumenta "
                    "la duración de la escena."
                )

        coverage = (
            total_estimated_seconds / target_duration
            if target_duration > 0 else 0.0
        )
        reports[language] = {
            "total_words": total_words,
            "estimated_voice_seconds": round(total_estimated_seconds, 2),
            "coverage": round(coverage, 4),
            "scenes": scene_reports,
        }

        if coverage < min_episode_coverage:
            errors.append(
                f"{language}: la voz cubre solo {coverage:.1%} del episodio; "
                f"mínimo {min_episode_coverage:.0%}."
            )
        if coverage > 1.0:
            errors.append(
                f"{language}: la duración hablada estimada supera el objetivo "
                "total del episodio."
            )

    return {
        "ok": not errors,
        "target_duration_seconds": round(target_duration, 2),
        "planned_duration_seconds": round(planned_duration, 2),
        "words_per_minute": float(words_per_minute),
        "line_gap_seconds": float(line_gap_seconds),
        "languages": reports,
        "errors": errors,
    }
