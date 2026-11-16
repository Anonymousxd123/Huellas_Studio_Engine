"""Procedurally drawn props in the episode's cel style (dark outline, flat
fills with one shade and one highlight), rendered supersampled for clean edges.
"""

import numpy as np
from PIL import Image, ImageDraw

SUPERSAMPLE = 4
OUTLINE = (44, 30, 32, 255)


def _finish(image, size):
    return image.resize(size, Image.Resampling.LANCZOS)


def draw_glass(height):
    """A drinking glass (tumbler) with water, `height` px tall. Bottom-centre anchored."""
    h = max(8, int(round(height)))
    w = int(round(h * 0.68))
    s = SUPERSAMPLE
    W, H = w * s, h * s
    image = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    line = max(2, int(round(H * 0.035)))
    top_half, bottom_half = W * 0.47, W * 0.37
    cx = W / 2
    body = [(cx - top_half, line), (cx + top_half, line),
            (cx + bottom_half, H - line), (cx - bottom_half, H - line)]
    draw.polygon(body, fill=(205, 232, 245, 95))
    # Water up to 58% of the height.
    level = H * 0.42
    t = (level - line) / (H - 2 * line)
    half_at_level = top_half + (bottom_half - top_half) * t
    water = [(cx - half_at_level, level), (cx + half_at_level, level),
             (cx + bottom_half, H - line), (cx - bottom_half, H - line)]
    draw.polygon(water, fill=(120, 190, 235, 150))
    draw.line([(cx - half_at_level, level), (cx + half_at_level, level)],
              fill=(80, 150, 205, 230), width=max(1, line // 2))
    # Thick base and highlight streak.
    draw.rectangle([cx - bottom_half, H - line * 3.2, cx + bottom_half, H - line],
                   fill=(225, 240, 250, 170))
    draw.line([(cx - top_half * 0.62, H * 0.12), (cx - bottom_half * 0.62, H * 0.82)],
              fill=(255, 255, 255, 210), width=max(2, int(line * 1.1)))
    draw.line(body + [body[0]], fill=OUTLINE, width=line, joint="curve")
    return _finish(image, (w, h))


def draw_bone_toy(length, angle=0.0):
    """A red rubber bone toy, `length` px long; centre-anchored, rotated `angle` deg."""
    L = max(12, int(round(length)))
    s = SUPERSAMPLE
    W, H = L * s, int(L * 0.36) * s
    image = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    line = max(2, int(round(H * 0.07)))
    r = H * 0.26
    shaft = (r * 1.3, H * 0.33, W - r * 1.3, H * 0.67)
    knobs = [(r * 1.05, H * 0.27), (r * 1.05, H * 0.73),
             (W - r * 1.05, H * 0.27), (W - r * 1.05, H * 0.73)]
    base, shade, light = (214, 58, 64, 255), (170, 36, 48, 255), (246, 128, 120, 255)
    # Outline pass (grown shapes), then fills.
    for (x, y) in knobs:
        draw.ellipse((x - r - line, y - r - line, x + r + line, y + r + line), fill=OUTLINE)
    draw.rectangle((shaft[0], shaft[1] - line, shaft[2], shaft[3] + line), fill=OUTLINE)
    for (x, y) in knobs:
        draw.ellipse((x - r, y - r, x + r, y + r), fill=base)
    draw.rectangle(shaft, fill=base)
    # Cel shade on the lower half, highlight on the upper half.
    draw.rectangle((shaft[0], H * 0.53, shaft[2], shaft[3]), fill=shade)
    for (x, y) in knobs[1::2]:
        draw.pieslice((x - r, y - r, x + r, y + r), 20, 160, fill=shade)
    draw.line([(shaft[0] + r * 0.4, H * 0.41), (shaft[2] - r * 0.4, H * 0.41)],
              fill=light, width=max(2, int(line * 1.2)))
    toy = _finish(image, (L, int(L * 0.36)))
    return toy.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)


def to_premultiplied(image):
    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32) / 255.0
    rgba[..., :3] *= rgba[..., 3:4]
    return rgba


PROP_DRAWERS = {"glass": draw_glass}
