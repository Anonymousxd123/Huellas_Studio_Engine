"""Objective checks for rig poses. Visual review is still required."""

import numpy as np
from scipy import ndimage as ndi

from .deform import _rotate, invert_joint, render_pose


def _holes(alpha, threshold=0.5):
    solid = alpha > threshold
    return ndi.binary_fill_holes(solid) & ~solid


def local_stretch(rig, joint_name, angle):
    """Area scale factor (forward Jacobian determinant) of the bend.

    1.0 = untouched, >1 = fur stretched, <1 = compressed. Evaluated only on
    opaque source pixels that are not hidden by the rigid overlay.
    """
    joint = next(j for j in rig.joints if j.name == joint_name)
    width, height = rig.size
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    src_x, src_y = invert_joint(joint, angle, xs, ys)
    dsx_dy, dsx_dx = np.gradient(src_x)
    dsy_dy, dsy_dx = np.gradient(src_y)
    det_inverse = dsx_dx * dsy_dy - dsx_dy * dsy_dx
    stretch = 1.0 / np.maximum(np.abs(det_inverse), 1e-6)
    sampled_alpha = ndi.map_coordinates(
        rig.rgba[..., 3], [src_y, src_x], order=1, mode="constant", cval=0.0
    )
    weight = ndi.map_coordinates(
        joint.weight, [src_y, src_x], order=1, mode="nearest"
    )
    region = (sampled_alpha > 0.5) & (weight > 0.01) & (weight < 0.99)
    if joint.overlay_alpha is not None:
        rx, ry = _rotate(xs, ys, joint.pivot, -np.deg2rad(angle))
        cover = ndi.map_coordinates(
            joint.overlay_alpha * rig.rgba[..., 3], [ry, rx], order=1,
            mode="constant", cval=0.0
        )
        region &= cover < 0.01  # bent pixels hidden under the rigid layer
    if not region.any():
        return 1.0, 1.0
    # 0.5/99.5 percentiles ignore single-pixel gradient noise at mask edges.
    values = stretch[region]
    return float(np.percentile(values, 0.5)), float(np.percentile(values, 99.5))


def evaluate_pose(rig, pose, protected_mask=None):
    """Return a dict of metrics for one pose against the rest pose.

    `protected_mask` marks source pixels that must not change (e.g. collar);
    pixels the rigid head legitimately covers are excluded from the check.
    """
    rest = render_pose(rig, {})
    frame = render_pose(rig, pose)
    source = rig.rgba.copy()
    source[..., :3] *= source[..., 3:4]

    metrics = {
        "rest_max_abs_error": float(np.abs(rest - source).max()),
        # Enclosed transparent pixels where the rest pose was opaque. Background
        # enclosed by e.g. an ear touching the tail is not a hole in the art.
        "new_interior_holes_px": int(
            (_holes(frame[..., 3]) & (rest[..., 3] > 0.5)).sum()
        ),
        "silhouette_area_change": float(
            abs((frame[..., 3] > 0.5).sum() - (rest[..., 3] > 0.5).sum())
            / max(1, (rest[..., 3] > 0.5).sum())
        ),
    }

    if protected_mask is not None and pose.get("breath", 0.0) == 0.0:
        covered = np.zeros(protected_mask.shape, dtype=bool)
        for joint in rig.joints:
            angle = pose.get(joint.name, 0.0)
            if joint.overlay_alpha is None or angle == 0:
                continue
            # Where the rotated overlay lands, occlusion is intended.
            height, width = protected_mask.shape
            ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
            rx, ry = _rotate(xs, ys, joint.pivot, -np.deg2rad(angle))
            cover = ndi.map_coordinates(
                joint.overlay_alpha * rig.rgba[..., 3], [ry, rx], order=1,
                mode="constant", cval=0.0
            )
            covered |= cover > 0.01
        check = protected_mask & ~covered
        diff = np.abs(frame - source).max(axis=-1)
        metrics["protected_max_abs_error"] = (
            float(diff[check].max()) if check.any() else 0.0
        )
        metrics["protected_px_checked"] = int(check.sum())

    for joint in rig.joints:
        angle = pose.get(joint.name, 0.0)
        if angle:
            low, high = local_stretch(rig, joint.name, angle)
            metrics[f"{joint.name}_stretch_min"] = low
            metrics[f"{joint.name}_stretch_max"] = high
    return metrics
