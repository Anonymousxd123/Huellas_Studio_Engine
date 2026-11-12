import json
from pathlib import Path

from PIL import Image

from huellas_engine.animation_engine import (
    DISTILLED_SIGMAS,
    REQUIRED_NODES,
    build_ltx_i2v_workflow,
    load_motion_config,
    validate_animation_inputs,
)


def test_ltx_workflow_connects_image_conditioning_and_distilled_sampler():
    workflow = build_ltx_i2v_workflow(
        uploaded_image="input/scene.png",
        positive_prompt="A cartoon dog tilts its head.",
        negative_prompt="morphing, extra limbs",
        seed=1234,
    )

    assert workflow["5"]["inputs"]["image"] == "input/scene.png"
    assert workflow["6"]["inputs"]["image"] == ["5", 0]
    assert workflow["7"]["inputs"]["image"] == ["6", 0]
    assert workflow["7"]["inputs"]["length"] == 49
    assert workflow["8"]["inputs"]["positive"] == ["7", 0]
    assert workflow["10"]["inputs"]["float_list"] == ["9", 0]
    assert workflow["14"]["inputs"]["latent_image"] == ["7", 2]
    assert workflow["15"]["inputs"]["samples"] == ["14", 1]
    assert workflow["16"]["inputs"]["images"] == ["15", 0]
    assert workflow["9"]["inputs"]["string"] == DISTILLED_SIGMAS


def test_motion_config_has_action_prompt_for_each_episode_scene():
    config = load_motion_config()
    assert set(config["scenes"]) == {f"SC{i:03d}" for i in range(1, 9)}
    assert "head" in config["scenes"]["SC003"].lower()
    assert config["model"] == "ltxv-2b-0.9.6-distilled-04-25.safetensors"


def test_validate_animation_inputs_accepts_complete_local_pilot(tmp_path):
    episode_dir = tmp_path / "projects" / "episode_001"
    composed = episode_dir / "scenes" / "SC003" / "composed"
    composed.mkdir(parents=True)
    Image.new("RGB", (1280, 720), "white").save(
        composed / "SC003_composed.png"
    )
    (episode_dir / "episode.json").write_text(
        json.dumps({
            "episode_id": "episode_001",
            "scenes": [{"scene_id": "SC003"}],
        }),
        encoding="utf-8",
    )

    comfyui_dir = tmp_path / "ComfyUI"
    checkpoint_dir = comfyui_dir / "models" / "checkpoints"
    text_dir = comfyui_dir / "models" / "text_encoders"
    checkpoint_dir.mkdir(parents=True)
    text_dir.mkdir(parents=True)
    (checkpoint_dir / "ltxv-2b-0.9.6-distilled-04-25.safetensors").write_bytes(
        b"x" * 2048
    )
    (text_dir / "t5xxl_fp16.safetensors").write_bytes(b"x" * 2048)

    result = validate_animation_inputs(
        episode_dir, "SC003", comfyui_dir, width=512, height=288, frames=49
    )
    assert result["image_path"].name == "SC003_composed.png"
    assert result["checkpoint_path"].is_file()
    assert result["text_encoder_path"].is_file()


def test_validate_animation_inputs_rejects_invalid_frame_count(tmp_path):
    try:
        validate_animation_inputs(
            tmp_path, "SC003", tmp_path, width=512, height=288, frames=50
        )
    except ValueError as exc:
        assert "8n + 1" in str(exc)
    else:
        raise AssertionError("Expected invalid LTX frame count to be rejected")


def test_required_ltx_nodes_include_local_sigma_helpers():
    assert "LTXVImgToVideo" in REQUIRED_NODES
    assert "StringToFloatList" in REQUIRED_NODES
    assert "FloatToSigmas" in REQUIRED_NODES
