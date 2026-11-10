import json
from pathlib import Path

from PIL import Image

from huellas_engine.asset_manager import normalize_manifest
from huellas_engine.audio_engine import build_voice_manifest
from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.image_utils import prepare_reference_image
from huellas_engine.localization_engine import validate_locales
from huellas_engine.kokoro_engine import (
    load_voice_profiles, resolve_voice_settings, split_text_for_tts
)
from huellas_engine.scene_composer import SCENE_LAYOUTS, load_character
from huellas_engine.scene_engine import validate_episode
from huellas_engine.video_engine import build_animatic_command
from huellas_engine.subtitle_engine import (
    build_subtitle_timeline, build_subtitle_timeline_from_audio,
    format_srt_timestamp, render_srt, split_subtitle_text
)


def test_normalize_manifest_accepts_list():
    metadata, results = normalize_manifest([{"seed": 1, "images": []}])
    assert metadata == {}
    assert len(results) == 1


def test_normalize_manifest_rejects_invalid_results():
    try:
        normalize_manifest({"results": {}})
    except ValueError as exc:
        assert "results" in str(exc)
    else:
        raise AssertionError("Expected invalid manifest to raise ValueError")


def test_load_character_ignores_near_transparent_bbox_noise(tmp_path):
    image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 0, 0, 1))
    image.putpixel((10, 10), (255, 0, 0, 255))
    image.putpixel((20, 20), (255, 0, 0, 128))
    path = tmp_path / "character.png"
    image.save(path)

    result = load_character(path)
    assert result.size == (11, 11)
    assert result.getchannel("A").getbbox() == (0, 0, 11, 11)


def test_validate_episode_reports_duplicate_scene_ids():
    episode = {
        "target_duration_seconds": 120,
        "scenes": [
            {
                "scene_id": "SC001", "duration_seconds": 30,
                "location": "room", "characters": ["dog"],
                "action": "sits", "visual_prompt": "cartoon dog"
            },
            {
                "scene_id": "SC001", "duration_seconds": 30,
                "location": "room", "characters": ["cat"],
                "action": "sits", "visual_prompt": "cartoon cat"
            }
        ]
    }
    errors = validate_episode(episode)
    assert any("duplicado" in error for error in errors)


def test_composer_has_layout_for_all_eight_episode_scenes():
    expected = {f"SC{index:03d}" for index in range(1, 9)}
    assert set(SCENE_LAYOUTS) == expected
    for placements in SCENE_LAYOUTS.values():
        assert len(placements) == 2
        assert {item["asset"] for item in placements} == {
            "dog_master_rgba.png", "cat_master_rgba.png"
        }


def test_resolve_episode_dir_accepts_project_id(tmp_path):
    episode_dir = tmp_path / "projects" / "episode_002"
    episode_dir.mkdir(parents=True)
    (episode_dir / "episode.json").write_text("{}", encoding="utf-8")

    assert resolve_episode_dir("episode_002", tmp_path) == episode_dir.resolve()


def test_resolve_episode_dir_accepts_relative_path(tmp_path):
    episode_dir = tmp_path / "projects" / "episode_003"
    episode_dir.mkdir(parents=True)
    (episode_dir / "episode.json").write_text("{}", encoding="utf-8")

    assert resolve_episode_dir("projects/episode_003", tmp_path) == episode_dir.resolve()



def test_prepare_reference_image_uses_exact_canvas_dimensions(tmp_path):
    source = tmp_path / "source.png"
    destination = tmp_path / "prepared.png"
    Image.new("RGB", (200, 100), "white").save(source)

    result = prepare_reference_image(source, destination, 128, 128)

    with Image.open(result) as prepared:
        assert prepared.size == (128, 128)


def test_locale_validator_reports_incomplete_dialogue_without_crashing(tmp_path):
    episode_dir = tmp_path / "episode"
    (episode_dir / "locales").mkdir(parents=True)
    (episode_dir / "episode.json").write_text(
        '{"supported_languages":["es"],"scenes":[{"scene_id":"SC001"}]}',
        encoding="utf-8"
    )
    locale = {
        "language": "es",
        "episode": {"title": "Título", "description": "Descripción"},
        "scenes": {
            "SC001": {
                "title": "Escena",
                "narration": "Narración",
                "dialogue": [None]
            }
        }
    }
    (episode_dir / "locales" / "es.json").write_text(
        json.dumps(locale),
        encoding="utf-8"
    )

    errors = validate_locales(episode_dir)
    assert any("diálogo 1 incompleto" in error for error in errors)



def test_srt_timestamp_formats_milliseconds():
    assert format_srt_timestamp(65.432) == "00:01:05,432"


def test_subtitle_text_splits_into_two_lines_per_cue():
    segments = split_subtitle_text(
        "uno dos tres cuatro cinco seis siete ocho nueve diez",
        max_chars=12,
        max_lines=2
    )
    assert segments
    assert all(len(segment.splitlines()) <= 2 for segment in segments)
    assert all(len(line) <= 12 for segment in segments for line in segment.splitlines())


def test_subtitle_timeline_stays_within_scene_duration(tmp_path):
    episode_dir = tmp_path / "episode"
    (episode_dir / "locales").mkdir(parents=True)
    (episode_dir / "episode.json").write_text(
        json.dumps({
            "episode_id": "episode_test",
            "supported_languages": ["es"],
            "scenes": [{
                "scene_id": "SC001",
                "duration_seconds": 10,
                "location": "sala",
                "characters": ["dog"],
                "action": "habla",
                "visual_prompt": "perro"
            }]
        }),
        encoding="utf-8"
    )
    locale = {
        "language": "es",
        "episode": {"title": "Prueba", "description": "Prueba"},
        "scenes": {
            "SC001": {
                "title": "Prueba",
                "narration": "Este es un texto breve para probar los subtítulos.",
                "dialogue": [{"character": "dog", "text": "Hola, mundo."}]
            }
        }
    }
    (episode_dir / "locales" / "es.json").write_text(
        json.dumps(locale),
        encoding="utf-8"
    )

    timeline = build_subtitle_timeline(episode_dir, "es")
    assert timeline["cues"]
    assert all(cue["start"] < cue["end"] <= 10 for cue in timeline["cues"])
    assert "00:00:" in render_srt(timeline)



def test_voice_manifest_preserves_speaker_and_language_assignments(tmp_path):
    episode_dir = tmp_path / "episode"
    (episode_dir / "locales").mkdir(parents=True)
    (episode_dir / "episode.json").write_text(
        json.dumps({
            "episode_id": "episode_test",
            "supported_languages": ["es"],
            "scenes": [{
                "scene_id": "SC001",
                "duration_seconds": 10,
                "location": "sala",
                "characters": ["dog", "cat"],
                "action": "hablan",
                "visual_prompt": "dos personajes"
            }]
        }),
        encoding="utf-8"
    )
    locale = {
        "language": "es",
        "episode": {"title": "Prueba", "description": "Prueba"},
        "scenes": {
            "SC001": {
                "title": "Prueba",
                "narration": "Narración de prueba.",
                "dialogue": [
                    {"character": "dog", "text": "Hola."},
                    {"character": "cat", "text": "Adiós."}
                ]
            }
        }
    }
    (episode_dir / "locales" / "es.json").write_text(
        json.dumps(locale),
        encoding="utf-8"
    )

    path, manifest = build_voice_manifest(episode_dir, "es")
    assert path.is_file()
    assert manifest["provider"] is None
    assert manifest["total_jobs"] == 3
    assert [job["speaker_id"] for job in manifest["jobs"]] == [
        "narrator", "dog", "cat"
    ]
    assert all(job["language"] == "es" for job in manifest["jobs"])



def test_animatic_command_adds_silent_audio_and_soft_subtitles(tmp_path, monkeypatch):
    episode_dir = tmp_path / "episode"
    scene_dir = episode_dir / "scenes" / "SC001" / "composed"
    locale_dir = episode_dir / "locales"
    scene_dir.mkdir(parents=True)
    locale_dir.mkdir(parents=True)
    Image.new("RGB", (320, 180), "white").save(
        scene_dir / "SC001_composed.png"
    )
    (episode_dir / "episode.json").write_text(
        json.dumps({
            "episode_id": "episode_test",
            "supported_languages": ["es"],
            "scenes": [{
                "scene_id": "SC001",
                "duration_seconds": 5,
                "location": "sala",
                "characters": ["dog"],
                "action": "habla",
                "visual_prompt": "perro"
            }]
        }),
        encoding="utf-8"
    )
    locale = {
        "language": "es",
        "episode": {"title": "Prueba", "description": "Prueba"},
        "scenes": {
            "SC001": {
                "title": "Prueba",
                "narration": "Hola mundo.",
                "dialogue": []
            }
        }
    }
    (locale_dir / "es.json").write_text(json.dumps(locale), encoding="utf-8")
    monkeypatch.setattr(
        "huellas_engine.video_engine.shutil.which",
        lambda binary: "/usr/bin/ffmpeg"
    )

    command = build_animatic_command(episode_dir, "es")
    assert "anullsrc=channel_layout=stereo:sample_rate=48000" in command
    assert str(episode_dir / "subtitles" / "es.srt") in command
    assert "libx264" in command
    assert "mov_text" in command
    assert command.index("-filter_complex") > max(
        index for index, value in enumerate(command) if value == "-i"
    )



def test_kokoro_voice_profiles_map_daniela_and_akira_references():
    profile_path = (
        Path(__file__).resolve().parents[1]
        / "config" / "tts" / "voice_profiles.json"
    )
    profiles = load_voice_profiles(profile_path)

    assert profiles["languages"]["es"]["narrator"]["voice_id"] == "ef_dora"
    assert profiles["languages"]["es"]["narrator"]["reference"] == "Daniela"
    assert profiles["languages"]["en"]["narrator"]["voice_id"] == "af_bella"
    assert profiles["languages"]["en"]["narrator"]["reference"] == "Akira"
    assert profiles["languages"]["en"]["narrator"]["alternatives"][0]["voice_id"] == "af_heart"


def test_kokoro_resolves_character_voices_by_language():
    profiles = load_voice_profiles(
        Path(__file__).resolve().parents[1]
        / "config" / "tts" / "voice_profiles.json"
    )
    dog_job = {"kind": "dialogue", "character": "dog"}
    cat_job = {"kind": "dialogue", "character": "cat"}
    narration_job = {"kind": "narration"}

    assert resolve_voice_settings(profiles, "es", narration_job)["voice_id"] == "ef_dora"
    assert resolve_voice_settings(profiles, "en", narration_job)["voice_id"] == "af_bella"
    assert resolve_voice_settings(profiles, "es", dog_job)["voice_id"] == "em_alex"
    assert resolve_voice_settings(profiles, "en", cat_job)["voice_id"] == "af_sarah"


def test_kokoro_splits_long_text_without_losing_words():
    source = (
        "Primera oración de prueba. "
        + " ".join(f"palabra{i}" for i in range(80))
        + " Última oración."
    )
    chunks = split_text_for_tts(source, max_chars=80)
    assert len(chunks) > 2
    assert " ".join(chunks).replace("  ", " ") == source
    assert all(len(chunk) <= 80 for chunk in chunks)



def test_subtitles_use_measured_audio_timeline_when_available(tmp_path):
    episode_dir = tmp_path / "episode"
    (episode_dir / "locales").mkdir(parents=True)
    (episode_dir / "audio" / "es").mkdir(parents=True)
    (episode_dir / "episode.json").write_text(
        json.dumps({
            "episode_id": "episode_test",
            "supported_languages": ["es"],
            "scenes": [{
                "scene_id": "SC001",
                "duration_seconds": 5,
                "location": "sala",
                "characters": ["dog"],
                "action": "habla",
                "visual_prompt": "perro"
            }]
        }),
        encoding="utf-8"
    )
    locale = {
        "language": "es",
        "episode": {"title": "Prueba", "description": "Prueba"},
        "scenes": {
            "SC001": {
                "title": "Prueba",
                "narration": "Hola mundo.",
                "dialogue": []
            }
        }
    }
    (episode_dir / "locales" / "es.json").write_text(
        json.dumps(locale), encoding="utf-8"
    )
    (episode_dir / "audio" / "es" / "audio_timeline.json").write_text(
        json.dumps({
            "language": "es",
            "duration_seconds": 5,
            "cues": [{
                "scene_id": "SC001",
                "start": 1.0,
                "end": 3.0,
                "text": "Hola mundo desde Huellas Studio"
            }]
        }),
        encoding="utf-8"
    )

    timeline = build_subtitle_timeline_from_audio(
        episode_dir, "es", max_chars=10, max_lines=1
    )
    assert timeline["timing_basis"] == "measured_tts_clip_durations"
    assert timeline["cues"][0]["start"] == 1.0
    assert timeline["cues"][-1]["end"] == 3.0
    assert all(
        timeline["cues"][i]["end"] <= timeline["cues"][i + 1]["start"]
        for i in range(len(timeline["cues"]) - 1)
    )
