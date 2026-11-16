from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageChops
import json
import math
import subprocess
import shutil

ROOT = Path.cwd()
SOURCE = Path.home() / "Huellas_Studio_Assets/characters/rig_prep_v1/akira/akira_master_padded.png"
OUT = ROOT / "projects" / "episode_001" / "character_rigs" / "akira" / "v1"
FRAMES = OUT / "frames"

OUT.mkdir(parents=True, exist_ok=True)
FRAMES.mkdir(parents=True, exist_ok=True)

if not SOURCE.is_file():
    raise FileNotFoundError(SOURCE)

im = Image.open(SOURCE).convert("RGBA")
w, h = im.size

# -----------------------------
# Rig definition v1
# -----------------------------
# These coordinates are based on the approved cut line and are intentionally
# generous so the head overlaps the body enough during a small tilt.
head_polygon = [
    (350, 285),
    (430, 225),
    (545, 180),
    (675, 170),
    (810, 185),
    (930, 235),
    (1005, 315),
    (1015, 420),
    (995, 535),
    (945, 615),
    (860, 670),
    (770, 700),
    (680, 710),
    (585, 706),
    (505, 690),
    (430, 655),
    (370, 600),
    (335, 515),
    (330, 405),
    (338, 330),
]

pivot = (655, 665)

# body/collar remain stable in prototype v1
# head rotates over the body

# -----------------------------
# Build masks
# -----------------------------
head_mask = Image.new("L", (w, h), 0)
d = ImageDraw.Draw(head_mask)
d.polygon(head_polygon, fill=255)

# soften edges slightly
head_mask = head_mask.filter(ImageFilter.GaussianBlur(radius=1.5))

# expanded mask used to remove head from body
expanded_mask = head_mask.filter(ImageFilter.MaxFilter(size=9))

alpha = im.getchannel("A")

head_alpha = ImageChops.multiply(alpha, head_mask)
body_keep = ImageChops.invert(expanded_mask)
body_alpha = ImageChops.multiply(alpha, body_keep)

head = im.copy()
head.putalpha(head_alpha)

body = im.copy()
body.putalpha(body_alpha)

# Save masks and layers
head_mask.save(OUT / "akira_head_mask.png")
expanded_mask.save(OUT / "akira_body_cut_mask.png")
head.save(OUT / "akira_head.png")
body.save(OUT / "akira_body.png")

# Preview cut line
guide = im.copy()
guide_draw = ImageDraw.Draw(guide)
guide_draw.line(head_polygon + [head_polygon[0]], fill=(255, 40, 40, 255), width=6)
r = 15
px, py = pivot
guide_draw.ellipse((px-r, py-r, px+r, py+r), fill=(255,215,0,220), outline=(20,20,20,255), width=3)
guide.save(OUT / "akira_cutline_preview.png")

# -----------------------------
# Motion prototype
# -----------------------------
# Small readable head tilt
angles = [0, -2, -4, -6, -8, -10, -12, -14, -12, -10, -8, -6, -4, -2, 0]
# tiny breathing on body
breath_offsets = [0,0,1,1,1,2,2,2,2,2,1,1,1,0,0]

frames = []

for i, (angle, by) in enumerate(zip(angles, breath_offsets), start=1):
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    body_frame = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    body_frame.alpha_composite(body, (0, by))

    rotated_head = head.rotate(
        angle,
        resample=Image.Resampling.BICUBIC,
        center=pivot,
        expand=False,
        fillcolor=(0, 0, 0, 0),
    )

    canvas.alpha_composite(body_frame, (0, 0))
    canvas.alpha_composite(rotated_head, (0, 0))

    # flatten over light background for easy review
    bg = Image.new("RGBA", (w, h), (245, 245, 245, 255))
    flat = Image.alpha_composite(bg, canvas).convert("RGB")
    frame_path = FRAMES / f"frame_{i:03d}.png"
    flat.save(frame_path)
    frames.append(flat)

# GIF preview
gif_path = OUT / "akira_rig_preview.gif"
frames[0].save(
    gif_path,
    save_all=True,
    append_images=frames[1:],
    duration=90,
    loop=0,
)

# Contact sheet
thumb_w = 280
thumb_h = round(h * thumb_w / w)
sheet = Image.new("RGB", (thumb_w * 3, thumb_h * 2), "white")
selected = [frames[0], frames[4], frames[7], frames[8], frames[11], frames[14]]
for idx, fr in enumerate(selected):
    thumb = fr.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
    x = (idx % 3) * thumb_w
    y = (idx // 3) * thumb_h
    sheet.paste(thumb, (x, y))
sheet.save(OUT / "akira_rig_contact_sheet.jpg", quality=95)

# Optional MP4 assembly if ffmpeg exists
ffmpeg = shutil.which("ffmpeg")
mp4_path = OUT / "akira_rig_preview.mp4"
if ffmpeg:
    cmd = [
        ffmpeg, "-y",
        "-framerate", "12",
        "-i", str(FRAMES / "frame_%03d.png"),
        "-vf", "format=yuv420p",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        str(mp4_path),
    ]
    subprocess.run(cmd, check=False)

manifest = {
    "source": str(SOURCE),
    "output_dir": str(OUT),
    "pivot": pivot,
    "head_polygon": head_polygon,
    "frame_count": len(angles),
    "angles": angles,
}
(OUT / "akira_rig_manifest.json").write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("\nHUELLAS STUDIO - AKIRA RIG V1")
print("=" * 40)
print("Salida:", OUT)
print("Capas:")
print("-", OUT / "akira_head.png")
print("-", OUT / "akira_body.png")
print("Preview:")
print("-", OUT / "akira_cutline_preview.png")
print("-", OUT / "akira_rig_preview.gif")
print("-", OUT / "akira_rig_contact_sheet.jpg")
if mp4_path.exists():
    print("-", mp4_path)
print("\nProceso completado.")
