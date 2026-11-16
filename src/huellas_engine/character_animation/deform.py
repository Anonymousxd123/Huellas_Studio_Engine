"""Weight-field deformation of a painted character split into layers.

A rig is a partition of one painted image into layers (e.g. tail behind,
everything else in front). Each layer bends with its own joints. Because the
layers partition the image exactly, the rest pose reproduces the source.

Coordinates are (x, y) in image space with y pointing down. A positive joint
angle rotates counter-clockwise on screen (the top of a head moves to the
viewer's left).
"""

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage as ndi

FIXED_POINT_ITERATIONS = 3
NEWTON_ITERATIONS = 6


@dataclass
class Joint:
    name: str
    pivot: tuple  # (x, y) in prepared-rig pixels
    weight: np.ndarray  # float32 HxW, 1 = follows joint fully, 0 = anchored
    overlay_alpha: np.ndarray | None = None  # float32 HxW, rigid layer drawn on top
    max_angle: float = 20.0

    @property
    def support_bbox(self):
        """(x0, y0, x1, y1) of pixels with non-zero weight."""
        cached = getattr(self, "_support_bbox", None)
        if cached is None:
            cached = _mask_bbox(self.weight > 0)
            self._support_bbox = cached
        return cached

    def reach(self, angle_degrees, bbox):
        """Max distance any point of `bbox` can move under this joint."""
        x0, y0, x1, y1 = bbox
        px, py = self.pivot
        radius = max(np.hypot(x - px, y - py) for x in (x0, x1) for y in (y0, y1))
        return 2.0 * radius * abs(np.sin(np.deg2rad(angle_degrees) / 2.0))

    @property
    def weight_gradient(self):
        cached = getattr(self, "_weight_gradient", None)
        if cached is None:
            cached = tuple(g.astype(np.float32) for g in np.gradient(self.weight))
            self._weight_gradient = cached
        return cached


def _premultiply_planar(rgba):
    planar = rgba.copy()
    planar[..., :3] *= planar[..., 3:4]
    return np.ascontiguousarray(planar.transpose(2, 0, 1))


def _mask_bbox(mask):
    rows = np.nonzero(mask.any(axis=1))[0]
    cols = np.nonzero(mask.any(axis=0))[0]
    if rows.size == 0:
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def _grow(bbox, margin, width, height):
    x0, y0, x1, y1 = bbox
    m = int(np.ceil(margin)) + 2
    return max(0, x0 - m), max(0, y0 - m), min(width, x1 + m), min(height, y1 + m)


@dataclass
class Layer:
    name: str
    rgba: np.ndarray  # float32 HxWx4 straight alpha; zero outside this layer
    joints: list = field(default_factory=list)

    @property
    def premultiplied(self):
        cached = getattr(self, "_premultiplied", None)
        if cached is None:
            cached = _premultiply_planar(self.rgba)
            self._premultiplied = cached
        return cached

    @property
    def bbox(self):
        cached = getattr(self, "_bbox", None)
        if cached is None:
            cached = _mask_bbox(self.rgba[..., 3] > 0) or (0, 0, 0, 0)
            self._bbox = cached
        return cached


@dataclass
class PreparedRig:
    name: str
    rgba: np.ndarray  # float32 HxWx4, straight alpha: the full source image
    layers: list = field(default_factory=list)  # back-to-front
    breath_base_y: float = 0.0  # breathing scales vertically around this row
    breath_top_y: float = 0.0  # rows above this get the full breathing offset
    base_x: float = 0.0  # horizontal centre of the rest bbox (lean pivot x)

    @property
    def size(self):
        height, width = self.rgba.shape[:2]
        return width, height

    @property
    def joints(self):
        return [joint for layer in self.layers for joint in layer.joints]

    def layer_of(self, joint_name):
        for layer in self.layers:
            if any(j.name == joint_name for j in layer.joints):
                return layer
        raise KeyError(joint_name)


def _rotate(xs, ys, pivot, radians):
    """Rotate points counter-clockwise on screen by `radians` around pivot."""
    px, py = pivot
    dx = xs - px
    dy = ys - py
    cos = np.cos(radians)
    sin = np.sin(radians)
    return px + dx * cos + dy * sin, py - dx * sin + dy * cos


def _sample_scalar(field_values, xs, ys):
    return ndi.map_coordinates(
        field_values, [ys, xs], order=1, mode="nearest", prefilter=False
    )


def forward_joint(joint, angle_degrees, xs, ys):
    """Where source points (xs, ys) land after the weighted rotation."""
    weights = _sample_scalar(joint.weight, xs, ys)
    return _rotate(xs, ys, joint.pivot, np.deg2rad(angle_degrees) * weights)


def invert_joint(joint, angle_degrees, xs, ys, iterations=NEWTON_ITERATIONS):
    """Return source coordinates whose weighted rotation lands on (xs, ys).

    Solves f(p) = c + R(theta * w(p)) (p - c) = q. A few fixed-point steps
    give a starting guess; damped Newton steps with the analytic Jacobian then
    converge wherever the map is locally invertible. Where the bend folds
    (the compressed side of a tilt) there is no unique answer; the rigid
    overlay layer covers those pixels.
    """
    if angle_degrees == 0:
        return xs, ys
    theta = np.deg2rad(angle_degrees)
    px, py = joint.pivot
    grad_y, grad_x = joint.weight_gradient
    src_x, src_y = xs, ys
    for _ in range(FIXED_POINT_ITERATIONS):
        weights = _sample_scalar(joint.weight, src_x, src_y)
        src_x, src_y = _rotate(xs, ys, joint.pivot, -theta * weights)
    for _ in range(iterations):
        weights = _sample_scalar(joint.weight, src_x, src_y)
        wx = _sample_scalar(grad_x, src_x, src_y)
        wy = _sample_scalar(grad_y, src_x, src_y)
        phi = theta * weights
        cos = np.cos(phi)
        sin = np.sin(phi)
        dx = src_x - px
        dy = src_y - py
        fx = px + dx * cos + dy * sin - xs
        fy = py - dx * sin + dy * cos - ys
        v0 = -dx * sin + dy * cos
        v1 = -dx * cos - dy * sin
        j00 = cos + theta * v0 * wx
        j01 = sin + theta * v0 * wy
        j10 = -sin + theta * v1 * wx
        j11 = cos + theta * v1 * wy
        det = j00 * j11 - j01 * j10
        safe = np.abs(det) > 1e-3
        det = np.where(safe, det, 1.0)
        step_x = np.where(safe, (j11 * fx - j01 * fy) / det, 0.0)
        step_y = np.where(safe, (-j10 * fx + j00 * fy) / det, 0.0)
        # Damp very large steps so a bad local Jacobian cannot throw a pixel far.
        norm = np.hypot(step_x, step_y)
        scale = np.where(norm > 8.0, 8.0 / np.maximum(norm, 1e-6), 1.0)
        src_x = src_x - step_x * scale
        src_y = src_y - step_y * scale
    return src_x.astype(np.float32), src_y.astype(np.float32)


def _invert_breath(rig, breath, xs, ys):
    """Vertical squash/stretch: rows below base stay, rows above top shift fully."""
    if breath == 0:
        return xs, ys
    base = rig.breath_base_y
    top = rig.breath_top_y
    span = max(base - top, 1.0)
    # Forward: y' = y - breath * span * clamp((base - y) / span, 0, 1)
    # Approximate inverse with two fixed-point steps (offsets are a few px).
    src_y = ys
    for _ in range(2):
        t = np.clip((base - src_y) / span, 0.0, 1.0)
        src_y = ys + breath * span * t
    return xs, src_y


def _sample_rgba(premultiplied, xs, ys, order):
    channels = [
        ndi.map_coordinates(
            premultiplied[c], [ys, xs], order=order, mode="constant",
            cval=0.0, prefilter=order > 1
        )
        for c in range(4)
    ]
    return np.clip(np.stack(channels, axis=-1), 0.0, 1.0)


def _render_layer(layer, pose, bx, by, order, body_reach):
    """Render one layer into a full-size premultiplied frame.

    Work is limited to the region its pixels can reach this frame (layer bbox
    grown by the largest possible displacement) and, per joint, to where that
    joint has influence; outside those regions the maps are the identity.
    """
    height, width = bx.shape
    frame = np.zeros((height, width, 4), dtype=np.float32)
    if layer.bbox[2] <= layer.bbox[0]:
        return frame, None
    angles = []
    reach = body_reach
    for joint in layer.joints:
        angle = float(pose.get(joint.name, 0.0))
        if abs(angle) > joint.max_angle:
            raise ValueError(
                f"Ángulo {angle} fuera de rango para {joint.name} "
                f"(máx {joint.max_angle})"
            )
        angles.append(angle)
        reach += joint.reach(angle, layer.bbox)
    rx0, ry0, rx1, ry1 = _grow(layer.bbox, reach, width, height)
    roi = (slice(ry0, ry1), slice(rx0, rx1))
    src_x, src_y = bx[roi].copy(), by[roi].copy()
    for joint, angle in zip(layer.joints, angles):
        if angle == 0 or joint.support_bbox is None:
            continue
        sx0, sy0, sx1, sy1 = _grow(joint.support_bbox, joint.reach(angle, joint.support_bbox)
                                   + body_reach, width, height)
        sub = (slice(max(sy0, ry0) - ry0, max(min(sy1, ry1) - ry0, 0)),
               slice(max(sx0, rx0) - rx0, max(min(sx1, rx1) - rx0, 0)))
        if src_x[sub].size:
            src_x[sub], src_y[sub] = invert_joint(joint, angle, src_x[sub], src_y[sub])

    part = _sample_rgba(layer.premultiplied, src_x, src_y, order)

    for joint, angle in zip(layer.joints, angles):
        if joint.overlay_alpha is None or angle == 0:
            continue
        rigid_x, rigid_y = _rotate(bx[roi], by[roi], joint.pivot, -np.deg2rad(angle))
        top = _sample_rgba(layer.premultiplied, rigid_x, rigid_y, order)
        coverage = ndi.map_coordinates(
            joint.overlay_alpha, [rigid_y, rigid_x], order=1,
            mode="constant", cval=0.0, prefilter=False
        )[..., None]
        top *= coverage
        part = top + part * (1.0 - top[..., 3:4])
    frame[roi] = part
    return frame, roi


BODY_KEYS = {"breath", "lift", "lean"}


def _invert_body(rig, pose, xs, ys):
    """Whole-body transforms: breath, then lean about the base, then lift.

    lift is a fraction of the rest height (positive = up); lean is in degrees
    (positive = counter-clockwise on screen) around (base_x, breath_base_y).
    """
    lift = float(pose.get("lift", 0.0))
    lean = float(pose.get("lean", 0.0))
    if lift:
        ys = ys + lift * (rig.breath_base_y - rig.breath_top_y)
    if lean:
        xs, ys = _rotate(xs, ys, (rig.base_x, rig.breath_base_y), -np.deg2rad(lean))
    return _invert_breath(rig, float(pose.get("breath", 0.0)), xs, ys)


def render_pose(rig, pose=None, order=1):
    """Render the rig in a pose. Returns premultiplied float32 HxWx4.

    `pose` maps joint names to angles in degrees and may include "breath"
    (fraction of the chest-to-head span to lift, e.g. 0.004), "lift" and
    "lean" (see _invert_body).
    """
    pose = pose or {}
    width, height = rig.size
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)

    known = {j.name for j in rig.joints}
    for name in pose:
        if name not in BODY_KEYS and name not in known:
            raise KeyError(f"Articulación desconocida en la pose: {name}")

    # Forward order is joints first, then the body; invert in reverse.
    bx, by = _invert_body(rig, pose, xs, ys)
    span = rig.breath_base_y - rig.breath_top_y
    corner = max(np.hypot(x - rig.base_x, y - rig.breath_base_y)
                 for x in (0, width) for y in (0, height))
    body_reach = (abs(float(pose.get("lift", 0.0))) * span
                  + abs(float(pose.get("breath", 0.0))) * span
                  + 2.0 * corner * abs(np.sin(np.deg2rad(float(pose.get("lean", 0.0))) / 2.0)))
    result = np.zeros((height, width, 4), dtype=np.float32)
    for layer in rig.layers:
        frame, roi = _render_layer(layer, pose, bx, by, order, body_reach)
        if roi is not None:
            result[roi] = frame[roi] + result[roi] * (1.0 - frame[roi][..., 3:4])
    return result


def to_straight_uint8(premultiplied):
    alpha = premultiplied[..., 3:4]
    rgb = np.where(alpha > 1e-6, premultiplied[..., :3] / np.maximum(alpha, 1e-6), 0)
    out = np.concatenate([rgb, alpha], axis=-1)
    return np.clip(np.rint(out * 255.0), 0, 255).astype(np.uint8)
