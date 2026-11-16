"""Build rig-animated scene specs for a whole episode from its audio timeline."""

import hashlib
import json
from pathlib import Path

from functools import lru_cache

import numpy as np
from PIL import Image

from .choreography import scene_tracks
from .compositor import WIDE, CharacterPlacement, PropPlacement, SceneSpec, Shot, _rest_bbox
from .rig import load_rig

# Framing validated on all eight episode_001 backgrounds: Akira always on the
# left with his cropped tail on the frame edge and his cropped body below it.
LAYOUT = {
    "dog": {"rig": "config/rigs/akira.json", "center_x": 0.195, "bottom": 1.10, "height": 0.80},
    "cat": {
        "rig": "config/rigs/daniela.json", "center_x": 0.70, "bottom": 0.955, "height": 0.52,
        "contact_shadow": {"opacity": 0.38, "width": 0.78, "height": 0.06,
                           "offset_y": 0.015, "blur": 12},
    },
}
DRAW_ORDER = ("dog", "cat")

# Shots measured against LAYOUT (wide-frame pixels at 1920x1080). Zooms are
# chosen so neither character's art is upscaled beyond ~1.0x of its master:
# - dog_medium: push-in favouring Akira; his cropped body stays below frame
#   and his cropped tail stays on the left edge. Daniela remains in frame.
# - cat_close: Daniela close-up; Akira's right edge (x~749 + tilt) stays
#   >40 px outside the crop, Daniela keeps ~49 px of headroom.
DOG_MEDIUM = Shot("dog_medium", 1.17, (0.0, 1080 - 1080 / 1.17))
DOG_RIGHT_EDGE = 749.0  # Akira's rest bbox right edge in the wide frame (LAYOUT)
CLEARANCE = 40.0  # keep this many px of Akira outside a Daniela close-up

# Per-scene overrides of LAYOUT (measured on each background at 1920x1080).
SCENE_LAYOUT = {
    # SC004: Daniela sits on the coffee table (top surface y~760-840,
    # x~690-1460) so she can reach the glass; smaller because she is further
    # back than Akira.
    "SC004": {"cat": {"center_x": 0.693, "bottom": 0.755, "height": 0.33,
                      "contact_shadow": {"opacity": 0.32, "width": 0.78, "height": 0.05,
                                         "offset_y": 0.012, "blur": 7}}},
}
# Accessories painted onto the rig source (source px), moving with the head.
SCENE_ACCESSORIES = {
    "SC005": {"dog": [{"kind": "bone", "center": [772, 592], "length": 300, "angle": -6}]},
}


@lru_cache(maxsize=None)
def _source_bbox(rig_path):
    image = load_rig(rig_path).load_image()
    return _rest_bbox(np.asarray(image, dtype=np.float32) / 255.0)


def _wide_bbox(layout, rig_path, width, height):
    """Rest bbox of a character in wide-frame px, plus its rig scale."""
    sx0, sy0, sx1, sy1 = _source_bbox(str(rig_path))
    scale = layout["height"] * height / (sy1 - sy0)
    x0 = layout["center_x"] * width - (sx1 - sx0) * scale / 2
    y1 = layout["bottom"] * height
    return (x0, y1 - (sy1 - sy0) * scale, x0 + (sx1 - sx0) * scale, y1), scale


def cat_close_shot(bbox, art_scale, width, height):
    """Daniela close-up: ~85% of the frame height, no upscaling, Akira out."""
    x0, y0, x1, y1 = bbox
    zoom = 0.85 * height / (y1 - y0)
    zoom = max(zoom, width / (width - DOG_RIGHT_EDGE - CLEARANCE))  # keep Akira out
    zoom = round(min(zoom, 2.0, 0.98 / art_scale), 4)  # background and art sharpness
    crop_w, crop_h = width / zoom, height / zoom
    ox = min(max((x0 + x1) / 2 - crop_w / 2, DOG_RIGHT_EDGE + CLEARANCE), width - crop_w)
    oy = min(max((y0 + y1) / 2 - crop_h / 2, 0.0), height - crop_h)
    # Floor so the crop never exceeds the frame by a rounding hair.
    return Shot("cat_close", zoom, (np.floor(ox * 100) / 100, np.floor(oy * 100) / 100))


def resolve_background(episode_dir, scene_id):
    episode_dir = Path(episode_dir)
    metadata = episode_dir / "metadata" / f"{scene_id}_background.json"
    if metadata.is_file():
        images = json.loads(metadata.read_text(encoding="utf-8")).get("images") or []
        if images and Path(images[-1]).is_file():
            return Path(images[-1])
    candidates = sorted((episode_dir / "backgrounds").glob(f"*{scene_id}*.png"))
    if not candidates:
        raise FileNotFoundError(f"No hay fondo para {scene_id}")
    return candidates[-1]


def build_scene_specs(episode_dir, language, root, fps=24, width=1920, height=1080):
    """Return [(scene_id, start_seconds, SceneSpec)] in episode order."""
    episode_dir = Path(episode_dir)
    root = Path(root)
    episode = json.loads((episode_dir / "episode.json").read_text(encoding="utf-8"))
    timeline = json.loads(
        (episode_dir / "audio" / language / "audio_timeline.json").read_text(encoding="utf-8")
    )
    specs = []
    start = 0.0
    for scene in episode["scenes"]:
        scene_id = scene["scene_id"]
        cues = [c for c in timeline["cues"] if c["scene_id"] == scene_id]
        tracks = scene_tracks(dict(scene, start=start), cues)
        characters = []
        layouts = {}
        for role in DRAW_ORDER:
            if role not in scene.get("characters", DRAW_ORDER):
                continue
            layout = dict(LAYOUT[role], **SCENE_LAYOUT.get(scene_id, {}).get(role, {}))
            layouts[role] = layout
            characters.append(CharacterPlacement(
                rig_path=root / layout["rig"],
                center_x=layout["center_x"],
                bottom=layout["bottom"],
                height=layout["height"],
                tracks=tracks[role],
                contact_shadow=layout.get("contact_shadow"),
                accessories=SCENE_ACCESSORIES.get(scene_id, {}).get(role, []),
            ))
        cat_bbox, cat_scale = _wide_bbox(layouts["cat"], root / layouts["cat"]["rig"],
                                         width, height)
        shots = {"wide": WIDE, "dog_medium": DOG_MEDIUM,
                 "cat_close": cat_close_shot(cat_bbox, cat_scale, width, height)}
        props = []
        if "glass" in tracks["props"]:
            # Just left of Daniela's left front paw (source x 278 at the paw),
            # standing on the same surface; ~30% of her seated height.
            sx0 = _source_bbox(str(root / layouts["cat"]["rig"]))[0]
            paw_left = cat_bbox[0] + (278 - sx0) * cat_scale
            glass_h = 0.30 * (cat_bbox[3] - cat_bbox[1])
            props.append(PropPlacement(
                kind="glass", height=glass_h,
                base=(paw_left - glass_h * 0.34 - 3, cat_bbox[3] - 3),
                tracks=tracks["props"]["glass"],
            ))
        spec = SceneSpec(
            props=props,
            shots=[(t, shots[name]) for t, name in tracks["shots"]],
            scene_id=scene_id,
            background=resolve_background(episode_dir, scene_id),
            width=width, height=height, fps=fps,
            duration=float(scene["duration_seconds"]),
            characters=characters,
        )
        specs.append((scene_id, start, spec))
        start += float(scene["duration_seconds"])
    return specs


def spec_fingerprint(spec, extra=""):
    """Stable hash of everything that affects a scene's pixels."""
    payload = {
        "background": str(spec.background),
        "size": [spec.width, spec.height, spec.fps, spec.duration],
        "shots": [[t, shot.name, shot.zoom, list(shot.origin)] for t, shot in spec.shots],
        "props": [[p.kind, p.height, list(p.base),
                   {n: {"keys": [list(k) for k in t.keys], "sine": t.sine}
                    for n, t in sorted(p.tracks.items())}] for p in spec.props],
        "characters": [
            {
                "rig": Path(c.rig_path).read_text(encoding="utf-8"),
                "placement": [c.center_x, c.bottom, c.height],
                "accessories": c.accessories,
                "shadow": c.contact_shadow,
                "tracks": {
                    name: {"keys": [list(k) for k in t.keys], "sine": t.sine}
                    for name, t in sorted(c.tracks.items())
                },
            }
            for c in spec.characters
        ],
        "extra": extra,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


def chunk_ranges(frame_count, chunk_frames):
    return [(s, min(s + chunk_frames, frame_count)) for s in range(0, frame_count, chunk_frames)]
