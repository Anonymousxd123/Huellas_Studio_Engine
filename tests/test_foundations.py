from PIL import Image

from huellas_engine.asset_manager import normalize_manifest
from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.scene_composer import SCENE_LAYOUTS, load_character
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
