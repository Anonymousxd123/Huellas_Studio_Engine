"""Procedural eyelids for blinks, painted on the source before deformation.

Each eye's shape is taken from the art itself: the dark outline loop is
filled to get the eye interior, then grown to cover the outline (lashes
outside the loop are left alone). The lid colour is a smooth interpolation
of the fur around the eye, so it keeps the art's shading. The upper lid
slides down and the lower lid rises, following the eye's own top/bottom
contours column by column, until they meet on a gentle downward curve.
Painting happens on the rig's (scaled) source, so lids follow every joint.
"""

from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi

CLOSED_AT = 0.62  # closed line: this fraction of the way from top to bottom
LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)


@dataclass
class Eye:
    box: tuple  # (x0, y0, x1, y1) prepared-rig pixels
    mask: np.ndarray  # float32 soft coverage of the eye (box-sized)
    top: np.ndarray  # per-column top of the eye (box-relative y), nan if none
    bottom: np.ndarray  # per-column bottom
    lid: np.ndarray  # float32 (3, h, w) straight lid colour
    line_width: float
    line_rgb: np.ndarray  # float32 [3]


def build_eye(rgba, center, radii, line_width, line_rgb, dark_threshold=0.36):
    """Extract one eye near `center` (search window 1.5x `radii`)."""
    height, width = rgba.shape[:2]
    cx, cy = center
    rx, ry = radii
    pad = max(rx, ry) * 0.6
    x0, x1 = int(max(0, cx - rx - pad)), int(min(width, cx + rx + pad))
    y0, y1 = int(max(0, cy - ry - pad)), int(min(height, cy + ry + pad))
    patch = rgba[y0:y1, x0:x1]
    luma = patch[..., :3] @ LUMA
    dark = (luma < dark_threshold) & (patch[..., 3] > 0.5)
    filled = ndi.binary_fill_holes(dark)
    labels, count = ndi.label(filled)
    if count == 0:
        raise ValueError(f"No se encontró el contorno del ojo en {center}")
    ys, xs = np.mgrid[y0:y1, x0:x1]
    sizes = ndi.sum(np.ones_like(labels), labels, range(1, count + 1))
    # The eye is the large filled region containing (or nearest to) the centre.
    def score(k):
        region = labels == k
        return np.hypot(xs[region].mean() - cx, ys[region].mean() - cy) - 0.02 * sizes[k - 1] ** 0.5
    best = min((k for k in range(1, count + 1) if sizes[k - 1] > 0.2 * rx * ry), key=score)
    eye = labels == best
    # Thin strokes attached to the outline (lashes) are removed by an opening.
    radius = max(2, int(round(line_width * 0.9)))
    disk = (np.hypot(*np.mgrid[-radius:radius + 1, -radius:radius + 1]) <= radius)
    eye = ndi.binary_opening(eye, structure=disk)
    grow = 2  # also hides the outline's antialiased fringe
    covered = ndi.binary_dilation(eye, iterations=grow)
    mask = ndi.gaussian_filter(covered.astype(np.float32), 0.8)

    cols = covered.any(axis=0)
    top = np.full(covered.shape[1], np.nan, np.float32)
    bottom = np.full(covered.shape[1], np.nan, np.float32)
    rows = np.arange(covered.shape[0], dtype=np.float32)
    for c in np.nonzero(cols)[0]:
        r = rows[covered[:, c]]
        top[c], bottom[c] = r.min(), r.max() + 1
    # Smooth the contours along the eye so the lid edge is a clean curve
    # (lash bases make the raw per-column extents jagged).
    idx = np.nonzero(cols)[0]
    sigma_cols = max(2.0, 0.05 * idx.size)
    for arr in (top, bottom):
        arr[idx] = ndi.gaussian_filter1d(arr[idx], sigma_cols, mode="nearest")

    # Lid colour: normalised convolution of the surrounding fur (no lines).
    reach = max(4, int(round(line_width * 2)))
    ring = ndi.binary_dilation(covered, iterations=reach) & ~ndi.binary_dilation(
        covered, iterations=2)
    ring &= (luma > np.percentile(luma[ring], 30)) & (patch[..., 3] > 0.9)
    sigma = max(rx, ry) * 0.45
    weight = ndi.gaussian_filter(ring.astype(np.float32), sigma)
    lid = np.stack([
        ndi.gaussian_filter(patch[..., c] * ring, sigma) / np.maximum(weight, 1e-6)
        for c in range(3)
    ]).astype(np.float32)
    return Eye(box=(x0, y0, x1, y1), mask=mask, top=top, bottom=bottom, lid=lid,
               line_width=line_width, line_rgb=np.asarray(line_rgb, np.float32))


def paint_eyelids(planar, eyes, blink):
    """Copy of a planar premultiplied (4, H, W) image with lids at `blink` (0..1)."""
    blink = float(np.clip(blink, 0.0, 1.0))
    if blink <= 0.0 or not eyes:
        return planar
    out = planar.copy()
    for eye in eyes:
        x0, y0, x1, y1 = eye.box
        h, w = eye.mask.shape
        ys = np.arange(h, dtype=np.float32)[:, None] + 0.5
        valid = ~np.isnan(eye.top)
        top = np.where(valid, eye.top, 0.0)[None, :]
        bottom = np.where(valid, eye.bottom, 0.0)[None, :]
        closed = top + CLOSED_AT * (bottom - top)
        upper_edge = top + blink * (closed - top)
        lower_edge = bottom - blink * (bottom - closed)
        upper = np.clip(upper_edge - ys + 0.5, 0.0, 1.0)
        lower = np.clip(ys - lower_edge + 0.5, 0.0, 1.0)
        lid = eye.mask * np.maximum(upper, lower) * valid[None, :]
        # Taper the closing line toward the corners like a brush stroke.
        span = np.where(valid, bottom - top, 0.0)
        taper = np.clip(span / (np.nanmax(eye.bottom - eye.top) * 0.35), 0.0, 1.0)
        width = eye.line_width * (0.35 + 0.65 * taper)
        line = np.clip(width / 2.0 - np.abs(ys - upper_edge) + 0.5, 0.0, 1.0)
        line *= eye.mask * valid[None, :] * min(1.0, blink * 4.0)
        region = out[:, y0:y1, x0:x1]
        alpha = region[3]
        for c in range(3):
            region[c] = region[c] * (1.0 - lid) + eye.lid[c] * alpha * lid
            region[c] = region[c] * (1.0 - line) + eye.line_rgb[c] * alpha * line
    return out
