"""Render a character rig test: debug overlays, a tilt cycle, zooms and metrics.

Example:
    python scripts/render_rig_preview.py --rig config/rigs/akira.json \
        --out projects/episode_001/character_rigs/akira/v3 --peak 12
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from huellas_engine.character_animation import (  # noqa: E402
    Track, load_rig, prepare_rig, render_pose,
)
from huellas_engine.character_animation.deform import to_straight_uint8  # noqa: E402
from huellas_engine.character_animation.qa import evaluate_pose  # noqa: E402
from huellas_engine.character_animation.rig import polygon_mask  # noqa: E402

CHECKER = (236, 236, 236)


def flatten(frame_premultiplied, color=CHECKER):
    rgb = frame_premultiplied[..., :3] + (
        1.0 - frame_premultiplied[..., 3:4]
    ) * (np.array(color, dtype=np.float32) / 255.0)
    return Image.fromarray(np.clip(np.rint(rgb * 255), 0, 255).astype(np.uint8))


def debug_overlay(definition, rig):
    base = Image.fromarray(to_straight_uint8(
        np.concatenate([rig.rgba[..., :3] * rig.rgba[..., 3:4],
                        rig.rgba[..., 3:4]], axis=-1)
    )).convert("RGBA")
    canvas = Image.new("RGBA", base.size, (40, 40, 40, 255))
    canvas.alpha_composite(base)
    for jd, joint in zip(definition.joints, rig.joints):
        heat = np.zeros((*joint.weight.shape, 4), dtype=np.uint8)
        heat[..., 0] = 255
        heat[..., 3] = (joint.weight * 110).astype(np.uint8)
        canvas.alpha_composite(Image.fromarray(heat))
        draw = ImageDraw.Draw(canvas)
        draw.line(jd.rigid_polygon + [jd.rigid_polygon[0]], fill=(255, 60, 60, 255), width=3)
        draw.line(jd.anchor_polygon + [jd.anchor_polygon[0]], fill=(40, 170, 255, 255), width=3)
        px, py = jd.pivot
        draw.ellipse((px - 10, py - 10, px + 10, py + 10), fill=(255, 215, 0, 255),
                     outline=(0, 0, 0, 255), width=2)
    return canvas.convert("RGB")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rig", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--joint", default="head")
    parser.add_argument("--peak", type=float, default=12.0)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--zoom", nargs=4, type=int, metavar=("X0", "Y0", "X1", "Y1"),
                        help="Region (source px) for the seam close-up")
    args = parser.parse_args()

    definition = load_rig(args.rig)
    rig = prepare_rig(definition)
    out = Path(args.out)
    frames_dir = out / "frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)

    debug_overlay(definition, rig).save(out / f"{rig.name}_rig_debug.png")

    peak = args.peak
    track = Track(keys=[
        (0.0, 0.0), (0.4, 0.0), (1.4, peak, "ease_in_out"), (2.2, peak, "hold"),
        (3.0, -peak * 0.35, "ease_in_out"), (3.6, -peak * 0.35, "hold"),
        (4.4, 0.0, "ease_in_out"), (4.8, 0.0),
    ])
    breath = Track(sine={"amplitude": 0.004, "period": 2.4})
    duration = 4.8
    count = round(duration * args.fps)
    frames = []
    for index in range(count):
        t = index / args.fps
        pose = {args.joint: track.value(t), "breath": breath.value(t)}
        image = flatten(render_pose(rig, pose))
        image.save(frames_dir / f"frame_{index:04d}.png")
        frames.append((pose, image))

    # Key poses at full size and seam close-ups.
    key_poses = {"rest": 0.0, "peak": peak, "counter": -peak * 0.35}
    zoom = args.zoom
    tiles = []
    metrics = {}
    protected = None
    for jd in definition.joints:
        mask = polygon_mask(rig.size, jd.anchor_polygon) & (rig.rgba[..., 3] > 0.5)
        protected = mask if protected is None else protected | mask
    for label, angle in key_poses.items():
        pose = {args.joint: angle}
        frame = render_pose(rig, pose)
        image = flatten(frame)
        image.save(out / f"{rig.name}_pose_{label}.png")
        metrics[label] = evaluate_pose(rig, pose, protected_mask=protected)
        if zoom:
            tiles.append(image.crop(tuple(zoom)))
    if tiles:
        tw, th = tiles[0].size
        sheet = Image.new("RGB", (tw * len(tiles), th), "white")
        for i, tile in enumerate(tiles):
            sheet.paste(tile, (i * tw, 0))
        sheet.save(out / f"{rig.name}_seam_zoom.png")

    thumb_w = 300
    picks = np.linspace(0, len(frames) - 1, 8).round().astype(int)
    thumb_h = round(frames[0][1].height * thumb_w / frames[0][1].width)
    sheet = Image.new("RGB", (thumb_w * 4, thumb_h * 2), "white")
    for i, k in enumerate(picks):
        thumb = frames[k][1].resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        sheet.paste(thumb, ((i % 4) * thumb_w, (i // 4) * thumb_h))
    sheet.save(out / f"{rig.name}_contact_sheet.jpg", quality=92)

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        subprocess.run([
            ffmpeg, "-y", "-loglevel", "error", "-framerate", str(args.fps),
            "-i", str(frames_dir / "frame_%04d.png"),
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
            "-c:v", "libx264", "-crf", "16", str(out / f"{rig.name}_tilt_preview.mp4"),
        ], check=True)

    report = {"rig": str(Path(args.rig)), "peak": peak, "frames": count, "metrics": metrics}
    (out / f"{rig.name}_qa.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
