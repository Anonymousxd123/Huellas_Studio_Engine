import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from huellas_engine.character_animation import Track, load_rig, prepare_rig, render_pose
from huellas_engine.character_animation.deform import forward_joint, invert_joint
from huellas_engine.character_animation.qa import evaluate_pose
from huellas_engine.character_animation.rig import (
    build_weight_field, max_boundary_jump, polygon_mask,
)

ROOT = Path(__file__).resolve().parents[1]


def _synthetic_character(tmp_path):
    """A 'dog' with a round head on a neck and a body with a collar stripe."""
    size = (240, 320)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((70, 150, 170, 310), fill=(230, 190, 110, 255))  # body
    draw.rectangle((95, 110, 145, 170), fill=(245, 225, 180, 255))  # neck
    draw.rectangle((70, 165, 170, 178), fill=(40, 90, 200, 255))  # collar
    draw.ellipse((60, 20, 180, 130), fill=(230, 190, 110, 255), outline=(30, 20, 20, 255), width=3)
    draw.ellipse((95, 60, 108, 73), fill=(40, 25, 20, 255))  # eyes
    draw.ellipse((132, 60, 145, 73), fill=(40, 25, 20, 255))
    source = tmp_path / "character.png"
    image.save(source)
    rig_path = tmp_path / "rig.json"
    rig_path.write_text(json.dumps({
        "name": "synthetic",
        "source": str(source),
        "joints": [{
            "name": "head",
            "pivot": [120, 140],
            "max_angle": 16,
            "smoothing_sigma": 0,
            "rigid_polygon": [[0, 0], [240, 0], [240, 115], [0, 115]],
            "anchor_polygon": [[0, 160], [240, 160], [240, 320], [0, 320]],
        }],
    }), encoding="utf-8")
    return rig_path


def test_rest_pose_reproduces_source_exactly(tmp_path):
    rig = prepare_rig(load_rig(_synthetic_character(tmp_path)))
    rest = render_pose(rig, {})
    source = rig.rgba.copy()
    source[..., :3] *= source[..., 3:4]
    assert np.abs(rest - source).max() == 0.0


def test_weight_field_is_continuous_and_bounded(tmp_path):
    definition = load_rig(_synthetic_character(tmp_path))
    joint = definition.joints[0]
    size = (240, 320)
    rigid = polygon_mask(size, joint.rigid_polygon)
    anchor = polygon_mask(size, joint.anchor_polygon)
    for sigma in (0.0, 2.0):
        weight = build_weight_field(rigid, anchor, sigma)
        assert weight[rigid].min() == 1.0
        assert weight[anchor].max() == 0.0
        assert 0.0 <= weight.min() and weight.max() <= 1.0
        assert max_boundary_jump(weight, rigid, anchor) < 0.06


def test_weight_field_rejects_overlapping_regions():
    region = np.zeros((10, 10), dtype=bool)
    region[2:6, 2:6] = True
    with pytest.raises(ValueError):
        build_weight_field(region, region.copy(), 0)


def test_inverse_map_matches_forward_map(tmp_path):
    rig = prepare_rig(load_rig(_synthetic_character(tmp_path)))
    joint = rig.joints[0]
    height, width = joint.weight.shape
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    for angle in (12.0, -12.0):
        src_x, src_y = invert_joint(joint, angle, xs, ys)
        fx, fy = forward_joint(joint, angle, src_x, src_y)
        residual = np.hypot(fx - xs, fy - ys)
        neck = (ys > 110) & (ys < 165) & (xs > 90) & (xs < 150)
        assert np.percentile(residual[neck], 99) < 0.5


def test_tilt_keeps_collar_fixed_and_opens_no_holes(tmp_path):
    rig = prepare_rig(load_rig(_synthetic_character(tmp_path)))
    collar = np.zeros(rig.rgba.shape[:2], dtype=bool)
    collar[166:178, 72:169] = True
    for angle in (12.0, -12.0):
        metrics = evaluate_pose(rig, {"head": angle}, protected_mask=collar)
        assert metrics["new_interior_holes_px"] == 0
        assert metrics["protected_max_abs_error"] < 0.02
        assert metrics["silhouette_area_change"] < 0.03


def test_tilt_moves_head_in_expected_direction(tmp_path):
    rig = prepare_rig(load_rig(_synthetic_character(tmp_path)))
    def head_top_x(frame):
        rows = np.nonzero(frame[..., 3] > 0.5)
        top = rows[0].min()
        return rows[1][rows[0] == top].mean()
    rest_x = head_top_x(render_pose(rig, {}))
    assert head_top_x(render_pose(rig, {"head": 12})) < rest_x - 5
    assert head_top_x(render_pose(rig, {"head": -12})) > rest_x + 5


def test_pose_validation(tmp_path):
    rig = prepare_rig(load_rig(_synthetic_character(tmp_path)))
    with pytest.raises(ValueError):
        render_pose(rig, {"head": 30})
    with pytest.raises(KeyError):
        render_pose(rig, {"tail": 5})


def test_breath_lifts_upper_body_only(tmp_path):
    rig = prepare_rig(load_rig(_synthetic_character(tmp_path)))
    frame = render_pose(rig, {"breath": 0.02})
    rest = render_pose(rig, {})
    top_rest = np.nonzero(rest[..., 3].max(axis=1) > 0.5)[0].min()
    top_frame = np.nonzero(frame[..., 3].max(axis=1) > 0.5)[0].min()
    assert top_frame < top_rest
    assert np.abs(frame[-12:] - rest[-12:]).max() < 0.05


def test_track_easing_and_holds():
    track = Track(keys=[(0.0, 0.0), (1.0, 10.0, "ease_in_out"), (2.0, 10.0, "hold")])
    assert track.value(-1) == 0.0
    assert track.value(0.5) == pytest.approx(5.0)
    assert track.value(1.5) == 10.0
    assert track.value(5) == 10.0
    samples = [track.value(t / 20) for t in range(21)]
    assert samples == sorted(samples)


def test_back_out_overshoots_then_settles():
    track = Track(keys=[(0.0, 0.0), (1.0, 10.0, "back_out")])
    values = [track.value(t / 100) for t in range(101)]
    assert max(values) > 10.0
    assert max(values) < 11.0
    assert values[-1] == pytest.approx(10.0)


def test_track_rejects_unsorted_keys_and_unknown_easing():
    with pytest.raises(ValueError):
        Track(keys=[(1.0, 0.0), (0.0, 1.0)])
    with pytest.raises(ValueError):
        Track(keys=[(0.0, 0.0), (1.0, 1.0, "bounce")])


@pytest.mark.skipif(
    not (Path.home() / "Huellas_Studio_Assets/characters/rig_prep_v1/akira/akira_master_padded.png").is_file(),
    reason="Asset maestro de Akira no disponible en este equipo",
)
def test_akira_rig_quality_gates():
    definition = load_rig(ROOT / "config/rigs/akira.json")
    rig = prepare_rig(definition, scale=0.5)
    anchor = polygon_mask(rig.size, definition.joints[0].anchor_polygon, 0.5)
    protected = anchor & (rig.rgba[..., 3] > 0.5)
    for angle in (12.0, -5.0):
        metrics = evaluate_pose(rig, {"head": angle}, protected_mask=protected)
        assert metrics["rest_max_abs_error"] == 0.0
        assert metrics["new_interior_holes_px"] <= 10
        assert metrics["protected_max_abs_error"] < 0.02
        assert metrics["head_stretch_max"] < 3.5


def _layered_rig(tmp_path):
    rig_path = _synthetic_character(tmp_path)
    data = json.loads(rig_path.read_text(encoding="utf-8"))
    image = Image.open(data["source"])
    ImageDraw.Draw(image).rectangle((185, 90, 215, 300), fill=(120, 120, 130, 255))  # tail
    image.save(data["source"])
    data["layers"] = [
        {"name": "tail", "region_polygon": [[182, 80], [240, 80], [240, 320], [182, 320]]},
        {"name": "main", "joints": data.pop("joints")},
    ]
    rig_path.write_text(json.dumps(data), encoding="utf-8")
    return rig_path


def test_layers_partition_source_exactly(tmp_path):
    rig = prepare_rig(load_rig(_layered_rig(tmp_path)))
    assert [layer.name for layer in rig.layers] == ["tail", "main"]
    total = sum(layer.rgba for layer in rig.layers)
    assert np.abs(total - rig.rgba).max() == 0.0
    source = rig.rgba.copy()
    source[..., :3] *= source[..., 3:4]
    assert np.abs(render_pose(rig, {}) - source).max() == 0.0


def test_static_tail_layer_does_not_follow_head(tmp_path):
    rig = prepare_rig(load_rig(_layered_rig(tmp_path)))
    frame = render_pose(rig, {"head": -12})
    rest = render_pose(rig, {})
    tail = (slice(200, 300), slice(186, 214))
    assert np.abs(frame[tail] - rest[tail]).max() < 1e-6


def test_rig_requires_exactly_one_remainder_layer(tmp_path):
    rig_path = _layered_rig(tmp_path)
    data = json.loads(rig_path.read_text(encoding="utf-8"))
    data["layers"][1]["region_polygon"] = [[0, 0], [10, 0], [10, 10]]
    rig_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_rig(rig_path)


@pytest.mark.skipif(
    not (Path.home() / "Huellas_Studio_Assets/characters/rig_prep_v1/daniela/daniela_master_padded.png").is_file(),
    reason="Asset maestro de Daniela no disponible en este equipo",
)
def test_daniela_rig_quality_gates():
    definition = load_rig(ROOT / "config/rigs/daniela.json")
    rig = prepare_rig(definition, scale=0.5)
    anchor = polygon_mask(rig.size, definition.joints[0].anchor_polygon, 0.5)
    protected = anchor & (rig.rgba[..., 3] > 0.5)
    for angle in (10.0, -4.0):
        metrics = evaluate_pose(rig, {"head": angle}, protected_mask=protected)
        assert metrics["rest_max_abs_error"] == 0.0
        assert metrics["new_interior_holes_px"] <= 20
        assert metrics["protected_max_abs_error"] < 0.02
        assert metrics["head_stretch_max"] < 2.0


def test_ease_in_out_back_starts_and_ends_at_rest_with_small_overshoot():
    track = Track(keys=[(0.0, 0.0), (1.0, 10.0, "ease_in_out_back")])
    values = [track.value(t / 1000) for t in range(1001)]
    assert values[1] - values[0] < 1e-6  # no pop when leaving a held key
    assert 10.2 < max(values) < 10.5
    assert values[-1] == pytest.approx(10.0)
    assert abs(values[-1] - values[-2]) < 1e-3


def test_scene_compositor_keeps_background_and_placement_stable(tmp_path):
    from huellas_engine.character_animation.compositor import (
        SceneSpec, load_background, place_characters, render_frame,
    )
    rig_path = _synthetic_character(tmp_path)
    background = tmp_path / "bg.png"
    Image.new("RGB", (160, 90), (90, 140, 200)).save(background)
    spec_path = tmp_path / "scene.json"
    spec_path.write_text(json.dumps({
        "scene_id": "T001", "background": "bg.png", "width": 320, "height": 180,
        "fps": 12, "duration": 1.0,
        "characters": [{
            "rig": rig_path.name, "center_x": 0.3, "bottom": 0.95, "height": 0.8,
            "tracks": {"head": {"keys": [[0.0, 0.0], [1.0, 10.0, "ease_in_out"]]}},
        }],
    }), encoding="utf-8")
    spec = SceneSpec.load(spec_path, tmp_path)
    placed = place_characters(spec)
    offsets = {tuple(item.offset) for item in placed}
    bg = load_background(spec)
    first, _ = render_frame(bg, placed, 0.0)
    last, poses = render_frame(bg, placed, 1.0)
    assert poses[0]["head"] == pytest.approx(10.0)
    assert {tuple(item.offset) for item in place_characters(spec)} == offsets
    right_side = (slice(None), slice(200, 320))  # far from the character
    expected = np.rint(bg[right_side][..., :3] * 255).astype(np.uint8)
    assert np.array_equal(first[right_side], expected)
    assert np.array_equal(last[right_side], expected)
    assert not np.array_equal(first, last)


def test_scene_rejects_tracks_for_unknown_joints(tmp_path):
    from huellas_engine.character_animation.compositor import SceneSpec, place_characters
    rig_path = _synthetic_character(tmp_path)
    Image.new("RGB", (32, 18)).save(tmp_path / "bg.png")
    spec_path = tmp_path / "scene.json"
    spec_path.write_text(json.dumps({
        "scene_id": "T002", "background": "bg.png", "width": 320, "height": 180,
        "fps": 12, "duration": 1.0,
        "characters": [{"rig": rig_path.name, "center_x": 0.3, "bottom": 0.95,
                        "height": 0.8, "tracks": {"tail": {"keys": [[0, 0]]}}}],
    }), encoding="utf-8")
    with pytest.raises(ValueError):
        place_characters(SceneSpec.load(spec_path, tmp_path))


def _cues():
    return [
        {"scene_id": "S1", "kind": "narration", "speaker_id": "narrator", "start": 10.0, "end": 50.0},
        {"scene_id": "S1", "kind": "dialogue", "speaker_id": "dog", "start": 50.3, "end": 53.0},
        {"scene_id": "S1", "kind": "dialogue", "speaker_id": "cat", "start": 53.3, "end": 56.0},
    ]


def test_choreography_is_deterministic_and_within_validated_limits():
    from huellas_engine.character_animation.choreography import LIMITS, IDLE_SWAY, scene_tracks
    scene = {"scene_id": "S1", "start": 10.0, "duration_seconds": 50.0}
    first = scene_tracks(scene, _cues())
    second = scene_tracks(scene, _cues())
    for role in ("dog", "cat"):
        assert first[role]["head"].keys == second[role]["head"].keys
        values = [first[role]["head"].value(i / 24) for i in range(50 * 24)]
        low, high = LIMITS[role]
        sway = IDLE_SWAY[role][0]
        assert low - sway - 1e-6 <= min(values) and max(values) <= high + sway + 1e-6
        steps = np.diff(values)
        assert np.abs(np.diff(steps)).max() < 0.4  # no pops
        assert len(first[role]["head"].keys) > 6  # gestures were scheduled


def test_speaker_moves_while_talking():
    from huellas_engine.character_animation.choreography import scene_tracks
    scene = {"scene_id": "S1", "start": 10.0, "duration_seconds": 50.0}
    tracks = scene_tracks(scene, _cues())
    dog = [tracks["dog"]["head"].value(40.3 + i / 24) for i in range(48)]
    assert max(dog) - min(dog) > 2.0
