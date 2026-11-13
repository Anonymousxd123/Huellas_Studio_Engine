"""Render a rig-animated scene (background + rigged characters) to MP4.

Example:
    python scripts/render_scene_animation.py \
        --spec config/animation/scenes/SC003_rig_pilot.json \
        --out projects/episode_001/animation/SC003/rig_pilot_v1
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from huellas_engine.character_animation.compositor import SceneSpec, render_scene  # noqa: E402


def git_revision():
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "src", "config/rigs",
                                "config/animation/scenes"], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.strip()
        return rev + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def contact_sheet(keyframes, path, columns=4, thumb_width=480):
    images = [Image.open(p) for p in keyframes]
    thumb_height = round(images[0].height * thumb_width / images[0].width)
    rows = (len(images) + columns - 1) // columns
    sheet = Image.new("RGB", (thumb_width * columns, thumb_height * rows), "white")
    for i, image in enumerate(images):
        thumb = image.resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        sheet.paste(thumb, ((i % columns) * thumb_width, (i // columns) * thumb_height))
    sheet.save(path, quality=92)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--keyframes", type=float, nargs="*",
                        default=[0.0, 0.85, 1.5, 2.2, 3.0, 3.7, 4.4, 4.9, 5.5, 6.5, 7.2, 7.9])
    parser.add_argument("--crf", type=int, default=16)
    args = parser.parse_args()

    spec = SceneSpec.load(ROOT / args.spec, ROOT)
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    keyframe_dir = out / "keyframes"
    mp4 = out / f"{spec.scene_id}_rig_pilot.mp4"

    started = time.time()

    def progress(done, total):
        if done % 24 == 0 or done == total:
            print(f"  frame {done}/{total}  ({time.time() - started:.0f}s)", flush=True)

    result = render_scene(spec, mp4, keyframe_dir=keyframe_dir,
                          keyframe_times=args.keyframes, crf=args.crf, progress=progress)
    keyframes = sorted(keyframe_dir.glob(f"{spec.scene_id}_t*.png"))
    contact_sheet(keyframes, out / f"{spec.scene_id}_contact_sheet.jpg")

    smoothness = {}
    for index, item in enumerate(result["placements"]):
        for joint in result["pose_log"][0]["poses"][index]:
            series = [frame["poses"][index][joint] for frame in result["pose_log"]]
            velocity = [b - a for a, b in zip(series, series[1:])]
            accel = [b - a for a, b in zip(velocity, velocity[1:])]
            smoothness[f"{item['rig']}.{joint}"] = {
                "max_abs_velocity_per_frame": round(max(map(abs, velocity), default=0), 4),
                "max_abs_accel_per_frame2": round(max(map(abs, accel), default=0), 4),
            }

    manifest = {
        "scene_id": spec.scene_id,
        "spec": args.spec,
        "spec_content": json.loads((ROOT / args.spec).read_text(encoding="utf-8")),
        "engine_revision": git_revision(),
        "output": str(mp4.relative_to(ROOT)) if mp4.is_relative_to(ROOT) else str(mp4),
        "render_seconds": round(time.time() - started, 1),
        "motion_smoothness": smoothness,
        **result,
    }
    (out / "render_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(smoothness, indent=2))
    print(f"\nOK {mp4}  ({manifest['render_seconds']}s, {result['frames']} frames)")


if __name__ == "__main__":
    main()
