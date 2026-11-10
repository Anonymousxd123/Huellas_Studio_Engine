import json

from PIL import Image

from huellas_engine.asset_manager import normalize_manifest
from huellas_engine.scene_composer import load_character
from huellas_engine.scene_engine import validate_episode


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
                "scene_id": "SC001",
                "duration_seconds": 30,
                "location": "room",
                "characters": ["dog"],
                "action": "sits",
                "visual_prompt": "cartoon dog"
            },
            {
                "scene_id": "SC001",
                "duration_seconds": 30,
                "location": "room",
                "characters": ["cat"],
                "action": "sits",
                "visual_prompt": "cartoon cat"
            }
        ]
    }
    errors = validate_episode(episode)
    assert any("duplicado" in error for error in errors)
