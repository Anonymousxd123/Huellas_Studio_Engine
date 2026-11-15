"""Per-frame scene compositing: static background + rigged characters."""

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .deform import render_pose
from .motion import Track, sample_tracks
from .rig import ALPHA_THRESHOLD, load_rig, prepare_rig


@dataclass
class CharacterPlacement:
    rig_path: Path
    center_x: float  # fraction of frame width for the rest-pose bbox centre
    bottom: float  # fraction of frame height for the rest-pose bbox bottom (>1 crops)
    height: float  # fraction of frame height for the rest-pose bbox height
    tracks: dict = field(default_factory=dict)
    contact_shadow: dict | None = None  # {"opacity", "width", "height", "offset_y"}


@dataclass
class SceneSpec:
    scene_id: str
    background: Path
    width: int
    height: int
    fps: int
    duration: float
    characters: list

    @classmethod
    def load(cls, path, root):
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        root = Path(root)
        characters = [
            CharacterPlacement(
                rig_path=root / c["rig"],
                center_x=float(c["center_x"]),
                bottom=float(c["bottom"]),
                height=float(c["height"]),
                tracks={name: Track.from_dict(t) for name, t in c.get("tracks", {}).items()},
                contact_shadow=c.get("contact_shadow"),
            )
            for c in data["characters"]
        ]
        return cls(
            scene_id=data["scene_id"],
            background=root / data["background"],
            width=int(data["width"]),
            height=int(data["height"]),
            fps=int(data["fps"]),
            duration=float(data["duration"]),
            characters=characters,
        )

    @property
    def frame_count(self):
        return round(self.duration * self.fps)


@dataclass
class PlacedRig:
    rig: object
    offset: tuple  # integer (x, y) of the rig canvas on the frame
    tracks: dict
    shadow: np.ndarray | None = None  # premultiplied frame-sized layer


def _rest_bbox(rgba):
    opaque = rgba[..., 3] > ALPHA_THRESHOLD / 255.0
    rows = np.nonzero(opaque.any(axis=1))[0]
    cols = np.nonzero(opaque.any(axis=0))[0]
    return cols[0], rows[0], cols[-1] + 1, rows[-1] + 1


def _contact_shadow(spec, bbox_frame, config):
    x0, y0, x1, y1 = bbox_frame
    width = (x1 - x0) * config.get("width", 0.8)
    height = (y1 - y0) * config.get("height", 0.05)
    cx = (x0 + x1) / 2 + (x1 - x0) * config.get("offset_x", 0.0)
    cy = y1 - (y1 - y0) * config.get("offset_y", 0.01)
    mask = Image.new("L", (spec.width, spec.height), 0)
    ImageDraw.Draw(mask).ellipse(
        (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2),
        fill=round(255 * config.get("opacity", 0.35)),
    )
    mask = mask.filter(ImageFilter.GaussianBlur(config.get("blur", 10)))
    alpha = np.asarray(mask, dtype=np.float32)[..., None] / 255.0
    tint = np.array([35, 25, 20], dtype=np.float32) / 255.0
    return np.concatenate([tint * alpha, alpha], axis=-1)


def place_characters(spec):
    placed = []
    for character in spec.characters:
        definition = load_rig(character.rig_path)
        source = np.asarray(definition.load_image(), dtype=np.float32) / 255.0
        x0, y0, x1, y1 = _rest_bbox(source)
        target_height = character.height * spec.height
        scale = target_height / (y1 - y0)
        rig = prepare_rig(definition, scale=scale)
        bx0, by0, bx1, by1 = _rest_bbox(rig.rgba)
        frame_x0 = character.center_x * spec.width - (bx1 - bx0) / 2
        frame_y1 = character.bottom * spec.height
        offset = (round(frame_x0 - bx0), round(frame_y1 - by1))
        known = {j.name for j in rig.joints} | {"breath"}
        unknown = set(character.tracks) - known
        if unknown:
            raise ValueError(f"Pistas sin articulación en {rig.name}: {sorted(unknown)}")
        shadow = None
        if character.contact_shadow:
            bbox_frame = (bx0 + offset[0], by0 + offset[1], bx1 + offset[0], by1 + offset[1])
            shadow = _contact_shadow(spec, bbox_frame, character.contact_shadow)
        placed.append(PlacedRig(rig=rig, offset=offset, tracks=character.tracks, shadow=shadow))
    return placed


def _composite(canvas, layer, offset):
    """Alpha-composite a premultiplied layer onto a premultiplied canvas, clipped."""
    ox, oy = offset
    lh, lw = layer.shape[:2]
    ch, cw = canvas.shape[:2]
    x0, y0 = max(ox, 0), max(oy, 0)
    x1, y1 = min(ox + lw, cw), min(oy + lh, ch)
    if x0 >= x1 or y0 >= y1:
        return
    src = layer[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
    dst = canvas[y0:y1, x0:x1]
    canvas[y0:y1, x0:x1] = src + dst * (1.0 - src[..., 3:4])


def load_background(spec):
    with Image.open(spec.background) as image:
        background = image.convert("RGB").resize(
            (spec.width, spec.height), Image.Resampling.LANCZOS
        )
    rgb = np.asarray(background, dtype=np.float32) / 255.0
    return np.concatenate([rgb, np.ones((*rgb.shape[:2], 1), np.float32)], axis=-1)


def render_frame(background, placed, t):
    canvas = background.copy()
    poses = []
    for item in placed:
        if item.shadow is not None:
            _composite(canvas, item.shadow, (0, 0))
    for item in placed:
        pose = sample_tracks(item.tracks, t)
        poses.append(pose)
        _composite(canvas, render_pose(item.rig, pose), item.offset)
    rgb = np.clip(np.rint(canvas[..., :3] * 255.0), 0, 255).astype(np.uint8)
    return rgb, poses


def encoder_command(ffmpeg, spec, output_mp4, crf):
    """Identical encoder settings for every chunk so they concat without re-encoding."""
    return [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{spec.width}x{spec.height}", "-r", str(spec.fps), "-i", "-",
        "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output_mp4),
    ]


def render_range(spec, placed, background, start_frame, end_frame, output_mp4, crf=16):
    """Render frames [start_frame, end_frame) of a scene to one MP4 chunk."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FileNotFoundError("No se encontró FFmpeg en PATH")
    output_mp4 = Path(output_mp4)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(encoder_command(ffmpeg, spec, output_mp4, crf),
                               stdin=subprocess.PIPE)
    try:
        for index in range(start_frame, end_frame):
            rgb, _ = render_frame(background, placed, index / spec.fps)
            process.stdin.write(rgb.tobytes())
    finally:
        process.stdin.close()
        code = process.wait()
    if code != 0:
        raise RuntimeError(f"FFmpeg terminó con código {code}")
    return output_mp4


def render_scene(spec, output_mp4, keyframe_dir=None, keyframe_times=(), crf=16,
                 progress=None):
    """Render the scene to MP4 (H.264, yuv420p) by piping raw frames to ffmpeg."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FileNotFoundError("No se encontró FFmpeg en PATH")
    output_mp4 = Path(output_mp4)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    background = load_background(spec)
    placed = place_characters(spec)

    keyframe_indices = {round(t * spec.fps): t for t in keyframe_times}
    if keyframe_dir:
        Path(keyframe_dir).mkdir(parents=True, exist_ok=True)

    process = subprocess.Popen(encoder_command(ffmpeg, spec, output_mp4, crf),
                               stdin=subprocess.PIPE)
    pose_log = []
    try:
        for index in range(spec.frame_count):
            t = index / spec.fps
            rgb, poses = render_frame(background, placed, t)
            pose_log.append({"t": round(t, 4), "poses": [
                {k: round(v, 4) for k, v in pose.items()} for pose in poses
            ]})
            process.stdin.write(rgb.tobytes())
            if keyframe_dir and index in keyframe_indices:
                Image.fromarray(rgb).save(
                    Path(keyframe_dir) / f"{spec.scene_id}_t{keyframe_indices[index]:05.2f}.png"
                )
            if progress:
                progress(index + 1, spec.frame_count)
    finally:
        process.stdin.close()
        code = process.wait()
    if code != 0:
        raise RuntimeError(f"FFmpeg terminó con código {code}")
    return {
        "frames": spec.frame_count,
        "placements": [
            {"rig": item.rig.name, "offset": list(item.offset), "size": list(item.rig.size)}
            for item in placed
        ],
        "pose_log": pose_log,
    }
