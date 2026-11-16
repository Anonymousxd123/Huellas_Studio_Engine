from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageChops
import json
import shutil
import subprocess

ROOT = Path.cwd()
SOURCE = Path.home() / "Huellas_Studio_Assets/characters/rig_prep_v1/akira/akira_master_padded.png"
OUT = ROOT / "projects" / "episode_001" / "character_rigs" / "akira" / "v2"
FRAMES = OUT / "frames"

OUT.mkdir(parents=True, exist_ok=True)
FRAMES.mkdir(parents=True, exist_ok=True)

if not SOURCE.is_file():
    raise FileNotFoundError(SOURCE)

im = Image.open(SOURCE).convert("RGBA")
w, h = im.size
alpha = im.getchannel("A")

# --------------------------------------------------
# RIG V2
# --------------------------------------------------
# Tighter head mask
head_polygon = [
    (355, 300),
    (430, 235),
    (540, 185),
    (675, 178),
    (810, 188),
    (935, 238),
    (1005, 315),
    (1018, 415),
    (995, 520),
    (945, 600),
    (875, 645),
    (800, 675),
    (710, 693),
    (615, 698),
    (530, 688),
    (455, 660),
    (390, 615),
    (345, 540),
    (330, 445),
    (332, 360),
]

# Static fur patch to hide the seam under the rotating head
neck_fill_polygon = [
    (455, 615),
    (505, 595),
    (575, 582),
    (655, 578),
    (735, 584),
    (810, 598),
    (860, 622),
    (850, 680),
    (805, 718),
    (730, 735),
    (650, 742),
    (570, 735),
    (505, 718),
    (460, 685),
    (440, 648),
]

pivot = (650, 655)

# --------------------------------------------------
# Build masks
# --------------------------------------------------
head_mask = Image.new("L", (w, h), 0)
ImageDraw.Draw(head_mask).polygon(head_polygon, fill=255)
head_mask = head_mask.filter(ImageFilter.GaussianBlur(radius=1.2))

expanded_head_mask = head_mask.filter(ImageFilter.MaxFilter(size=5))

neck_fill_mask = Image.new("L", (w, h), 0)
ImageDraw.Draw(neck_fill_mask).polygon(neck_fill_polygon, fill=255)
neck_fill_mask = neck_fill_mask.filter(ImageFilter.GaussianBlur(radius=4))

# Layers
head_alpha = ImageChops.multiply(alpha, head_mask)
body_alpha = ImageChops.multiply(alpha, ImageChops.invert(expanded_head_mask))
neck_fill_alpha = ImageChops.multiply(alpha, neck_fill_mask)

head = im.copy()
head.putalpha(head_alpha)

body = im.copy()
body.putalpha(body_alpha)

neck_fill = im.copy()
neck_fill.putalpha(neck_fill_alpha)

# Save masks/layers
head_mask.save(OUT / "akira_head_mask_v2.png")
expanded_head_mask.save(OUT / "akira_body_cut_mask_v2.png")
neck_fill_mask.save(OUT / "akira_neck_fill_mask_v2.png")
head.save(OUT / "akira_head_v2.png")
body.save(OUT / "akira_body_v2.png")
neck_fill.save(OUT / "akira_neck_fill_v2.png")

# Guide image
guide = im.copy()
gd = ImageDraw.Draw(guide)
gd.line(head_polygon + [head_polygon[0]], fill=(255, 40, 40, 255), width=6)
gd.line(neck_fill_polygon + [neck_fill_polygon[0]], fill=(0, 180, 255, 255), width=5)
r = 15
px, py = pivot
gd.ellipse((px-r, py-r, px+r, py+r), fill=(255,215,0,220), outline=(20,20,20,255), width=3)
guide.save(OUT / "akira_cutline_preview_v2.png")

# --------------------------------------------------
# Motion
# --------------------------------------------------
angles = [0, -2, -4, -6, -8, -10, -12, -10, -8, -6, -4, -2, 0]
breath_offsets = [0,0,1,1,1,2,2,2,1,1,1,0,0]

frames = []

for i, (angle, by) in enumerate(zip(angles, breath_offsets), start=1):
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    body_frame = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    body_frame.alpha_composite(body, (0, by))

    neck_frame = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    neck_frame.alpha_composite(neck_fill, (0, by))

    rotated_head = head.rotate(
        angle,
        resample=Image.Resampling.BICUBIC,
        center=pivot,
        expand=False,
        fillcolor=(0, 0, 0, 0),
    )

    canvas.alpha_composite(body_frame, (0, 0))
    canvas.alpha_composite(neck_frame, (0, 0))
    canvas.alpha_composite(rotated_head, (0, 0))

    bg = Image.new("RGBA", (w, h), (245, 245, 245, 255))
    flat = Image.alpha_composite(bg, canvas).convert("RGB")
    frame_path = FRAMES / f"frame_{i:03d}.png"
    flat.save(frame_path)
    frames.append(flat)

# GIF
gif_path = OUT / "akira_rig_preview_v2.gif"
frames[0].save(
    gif_path,
    save_all=True,
    append_images=frames[1:],
    duration=90,
    loop=0
)

# Contact sheet
thumb_w = 280
thumb_h = round(h * thumb_w / w)
sheet = Image.new("RGB", (thumb_w * 3, thumb_h * 2), "white")
selected_idx = [0, 2, 4, 6, 8, 12]
for idx, frame_index in enumerate(selected_idx):
    thumb = frames[frame_index].resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
    x = (idx % 3) * thumb_w
    y = (idx // 3) * thumb_h
    sheet.paste(thumb, (x, y))
sheet.save(OUT / "akira_rig_contact_sheet_v2.jpg", quality=95)

# MP4
ffmpeg = shutil.which("ffmpeg")
mp4_path = OUT / "akira_rig_preview_v2.mp4"
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
    "neck_fill_polygon": neck_fill_polygon,
    "angles": angles,
    "frame_count": len(angles),
}
(OUT / "akira_rig_manifest_v2.json").write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("\nHUELLAS STUDIO - AKIRA RIG V2")
print("=" * 40)
print("Salida:", OUT)
print("Archivos generados:")
for name in [
    "akira_head_v2.png",
    "akira_body_v2.png",
    "akira_neck_fill_v2.png",
    "akira_cutline_preview_v2.png",
    "akira_rig_preview_v2.gif",
    "akira_rig_contact_sheet_v2.jpg",
    "akira_rig_preview_v2.mp4",
]:
    path = OUT / name
    if path.exists():
        print("-", path)

print("\nProceso completado.")
