"""Build rig-animated scene specs for a whole episode from its audio timeline."""

import hashlib
import json
from pathlib import Path

from .choreography import scene_tracks
from .compositor import WIDE, CharacterPlacement, SceneSpec, Shot

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
SHOTS = {
    "wide": WIDE,
    "dog_medium": Shot("dog_medium", 1.17, (0.0, 1080 - 1080 / 1.17)),
    "cat_close": Shot("cat_close", 1.7, (1920 - 1920 / 1.7, 420.0)),
}


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
        for role in DRAW_ORDER:
            if role not in scene.get("characters", DRAW_ORDER):
                continue
            layout = LAYOUT[role]
            characters.append(CharacterPlacement(
                rig_path=root / layout["rig"],
                center_x=layout["center_x"],
                bottom=layout["bottom"],
                height=layout["height"],
                tracks=tracks[role],
                contact_shadow=layout.get("contact_shadow"),
            ))
        spec = SceneSpec(
            shots=[(t, SHOTS[name]) for t, name in tracks["shots"]],
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
        "characters": [
            {
                "rig": Path(c.rig_path).read_text(encoding="utf-8"),
                "placement": [c.center_x, c.bottom, c.height],
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
