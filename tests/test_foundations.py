import json

from PIL import Image

from huellas_engine.asset_manager import normalize_manifest
from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.image_utils import prepare_reference_image
from huellas_engine.localization_engine import validate_locales
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
