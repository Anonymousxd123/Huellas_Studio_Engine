"""Per-frame scene compositing: static background + rigged characters."""

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .deform import BODY_KEYS, render_pose
from .props import PROP_DRAWERS, to_premultiplied

SCREEN_KEYS = {"x"}  # handled by the compositor: horizontal move in wide-frame px
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
    accessories: list = field(default_factory=list)  # see rig.paste_accessories


@dataclass
class PropPlacement:
    """A prop drawn behind the characters. base = bottom-centre, wide-frame px."""

    kind: str
    height: float  # wide-frame px
    base: tuple
    tracks: dict = field(default_factory=dict)  # "x", "y" (px), "angle" (deg)


@dataclass(frozen=True)
class Shot:
    """A locked camera framing: crop of the wide frame scaled back to full size.

    `origin` is the crop's top-left in wide-frame pixels; the crop size is
    (width / zoom, height / zoom). Characters are re-rigged at the shot's
    scale (not upscaled), and the background is cropped from its original.
    """

    name: str = "wide"
    zoom: float = 1.0
    origin: tuple = (0.0, 0.0)


WIDE = Shot()


@dataclass
class SceneSpec:
    scene_id: str
    background: Path
    width: int
    height: int
    fps: int
    duration: float
    characters: list
    shots: list = field(default_factory=lambda: [(0.0, WIDE)])  # [(start_t, Shot)]
    props: list = field(default_factory=list)  # [PropPlacement]

    def shot_at(self, t):
        current = self.shots[0][1]
        for start, shot in self.shots:
            if t + 1e-9 >= start:
                current = shot
        return current

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
    zoom: float = 1.0


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


def _validate_shot(spec, shot):
    crop_w, crop_h = spec.width / shot.zoom, spec.height / shot.zoom
    ox, oy = shot.origin
    if shot.zoom < 1.0 or ox < -1e-6 or oy < -1e-6 \
            or ox + crop_w > spec.width + 1e-6 or oy + crop_h > spec.height + 1e-6:
        raise ValueError(f"Plano fuera del encuadre general: {shot}")


def place_characters(spec, shot=WIDE):
    _validate_shot(spec, shot)
    zoom = shot.zoom
    ox, oy = shot.origin
    placed = []
    for character in spec.characters:
        definition = load_rig(character.rig_path)
        source = np.asarray(definition.load_image(), dtype=np.float32) / 255.0
        sx0, sy0, sx1, sy1 = _rest_bbox(source)
        scale = character.height * spec.height / (sy1 - sy0)
        # Rig canvas origin in wide-frame pixels (float), then into the shot.
        wide_x = character.center_x * spec.width - (sx1 - sx0) * scale / 2 - sx0 * scale
        wide_y = character.bottom * spec.height - sy1 * scale
        rig = prepare_rig(definition, scale=scale * zoom, accessories=character.accessories)
        offset = (round((wide_x - ox) * zoom), round((wide_y - oy) * zoom))
        known = {j.name for j in rig.joints} | BODY_KEYS | SCREEN_KEYS
        unknown = set(character.tracks) - known
        if unknown:
            raise ValueError(f"Pistas sin articulación en {rig.name}: {sorted(unknown)}")
        shadow = None
        if character.contact_shadow:
            k = scale * zoom
            bbox_frame = (sx0 * k + offset[0], sy0 * k + offset[1],
                          sx1 * k + offset[0], sy1 * k + offset[1])
            config = dict(character.contact_shadow)
            config["blur"] = config.get("blur", 10) * zoom
            shadow = _contact_shadow(spec, bbox_frame, config)
        placed.append(PlacedRig(rig=rig, offset=offset, tracks=character.tracks,
                                shadow=shadow, zoom=zoom))
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


def load_background(spec, shot=WIDE):
    _validate_shot(spec, shot)
    with Image.open(spec.background) as image:
        image = image.convert("RGB")
        fx = image.width / spec.width
        fy = image.height / spec.height
        ox, oy = shot.origin
        box = (ox * fx, oy * fy,
               (ox + spec.width / shot.zoom) * fx, (oy + spec.height / shot.zoom) * fy)
        background = image.resize((spec.width, spec.height), Image.Resampling.LANCZOS, box=box)
    rgb = np.asarray(background, dtype=np.float32) / 255.0
    return np.concatenate([rgb, np.ones((*rgb.shape[:2], 1), np.float32)], axis=-1)


@dataclass
class PlacedProp:
    image: object  # PIL RGBA at shot scale
    base: tuple  # bottom-centre in shot px (float)
    zoom: float
    tracks: dict


def place_props(spec, shot=WIDE):
    placed = []
    for prop in spec.props:
        image = PROP_DRAWERS[prop.kind](prop.height * shot.zoom)
        base = ((prop.base[0] - shot.origin[0]) * shot.zoom,
                (prop.base[1] - shot.origin[1]) * shot.zoom)
        placed.append(PlacedProp(image=image, base=base, zoom=shot.zoom, tracks=prop.tracks))
    return placed


def _draw_prop(canvas, prop, t):
    values = sample_tracks(prop.tracks, t)
    image = prop.image
    angle = values.get("angle", 0.0)
    w, h = image.size
    if angle:
        # Rotate about the bottom centre (the contact point on the surface).
        pad = Image.new("RGBA", (w * 2, h * 2), (0, 0, 0, 0))
        pad.alpha_composite(image, (w // 2, 0))
        image = pad.rotate(angle, resample=Image.Resampling.BICUBIC, center=(w, h))
        anchor = (w, h)
    else:
        anchor = (w / 2, h)
    x = prop.base[0] + values.get("x", 0.0) * prop.zoom - anchor[0]
    y = prop.base[1] + values.get("y", 0.0) * prop.zoom - anchor[1]
    _composite(canvas, to_premultiplied(image), (round(x), round(y)))


def render_frame(background, placed, t, props=()):
    canvas = background.copy()
    poses = [sample_tracks(item.tracks, t) for item in placed]
    shifts = [round(pose.pop("x", 0.0) * item.zoom) for item, pose in zip(placed, poses)]
    for item, pose, dx in zip(placed, poses, shifts):
        if item.shadow is not None:
            # The contact shadow fades as the character hops off the floor.
            fade = float(np.clip(1.0 - 8.0 * pose.get("lift", 0.0), 0.4, 1.0))
            layer = item.shadow if fade == 1.0 else item.shadow * fade
            _composite(canvas, layer, (dx, 0))
    for prop in props:
        _draw_prop(canvas, prop, t)
    for item, pose, dx in zip(placed, poses, shifts):
        _composite(canvas, render_pose(item.rig, pose),
                   (item.offset[0] + dx, item.offset[1]))
    rgb = np.clip(np.rint(canvas[..., :3] * 255.0), 0, 255).astype(np.uint8)
    return rgb, poses


class SceneRenderer:
    """Renders any frame of a scene, preparing each shot's assets on demand."""

    def __init__(self, spec):
        self.spec = spec
        self._shots = {}

    def assets(self, shot):
        if shot not in self._shots:
            self._shots[shot] = (load_background(self.spec, shot),
                                 place_characters(self.spec, shot),
                                 place_props(self.spec, shot))
        return self._shots[shot]

    def frame(self, index):
        t = index / self.spec.fps
        shot = self.spec.shot_at(t)
        background, placed, props = self.assets(shot)
        rgb, poses = render_frame(background, placed, t, props)
        return rgb, poses, shot


def encoder_command(ffmpeg, spec, output_mp4, crf):
    """Identical encoder settings for every chunk so they concat without re-encoding."""
    return [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{spec.width}x{spec.height}", "-r", str(spec.fps), "-i", "-",
        "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output_mp4),
    ]


def render_range(renderer, start_frame, end_frame, output_mp4, crf=16):
    """Render frames [start_frame, end_frame) of a scene to one MP4 chunk."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FileNotFoundError("No se encontró FFmpeg en PATH")
    output_mp4 = Path(output_mp4)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(encoder_command(ffmpeg, renderer.spec, output_mp4, crf),
                               stdin=subprocess.PIPE)
    try:
        for index in range(start_frame, end_frame):
            rgb, _, _ = renderer.frame(index)
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
    renderer = SceneRenderer(spec)

    keyframe_indices = {round(t * spec.fps): t for t in keyframe_times}
    if keyframe_dir:
        Path(keyframe_dir).mkdir(parents=True, exist_ok=True)

    process = subprocess.Popen(encoder_command(ffmpeg, spec, output_mp4, crf),
                               stdin=subprocess.PIPE)
    pose_log = []
    try:
        for index in range(spec.frame_count):
            t = index / spec.fps
            rgb, poses, shot = renderer.frame(index)
            pose_log.append({"t": round(t, 4), "shot": shot.name, "poses": [
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
            for item in renderer.assets(spec.shots[0][1])[1]
        ],
        "pose_log": pose_log,
    }
