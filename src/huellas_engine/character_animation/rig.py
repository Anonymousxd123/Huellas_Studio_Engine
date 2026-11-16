"""Rig definitions (JSON) and their preparation into sampling-ready arrays."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from .deform import Joint, Layer, PreparedRig
from .eyes import build_eye

ALPHA_THRESHOLD = 8


@dataclass
class JointDefinition:
    name: str
    pivot: tuple
    rigid_polygon: list  # canvas region that follows the joint fully (w = 1)
    anchor_polygon: list  # canvas region that never moves with it (w = 0)
    overlay: bool = True  # draw the rigid part on top to occlude the anchor
    max_angle: float = 20.0
    smoothing_sigma: float = 4.0  # in source pixels
    overlay_feather: float = 1.5  # in source pixels


@dataclass
class LayerDefinition:
    """A piece of the source image. Layers are listed back-to-front.

    `region_polygon` claims source pixels for this layer; exactly one layer
    has no polygon and receives every pixel not claimed by another layer.
    """

    name: str
    region_polygon: list | None = None
    joints: list = field(default_factory=list)
    eyes: list = field(default_factory=list)  # dicts: center, radii, line_width, line_rgb


@dataclass
class RigDefinition:
    name: str
    source: Path
    layers: list = field(default_factory=list)
    breath_base_y: float | None = None  # source px; defaults to alpha bottom
    breath_top_y: float | None = None  # source px; defaults to alpha top
    notes: str = ""

    @property
    def joints(self):
        return [joint for layer in self.layers for joint in layer.joints]

    def load_image(self):
        if not self.source.is_file():
            raise FileNotFoundError(self.source)
        with Image.open(self.source) as image:
            return image.convert("RGBA")


def _joint_from_dict(j):
    return JointDefinition(
        name=j["name"],
        pivot=tuple(j["pivot"]),
        rigid_polygon=j["rigid_polygon"],
        anchor_polygon=j["anchor_polygon"],
        overlay=j.get("overlay", True),
        max_angle=float(j.get("max_angle", 20.0)),
        smoothing_sigma=float(j.get("smoothing_sigma", 4.0)),
        overlay_feather=float(j.get("overlay_feather", 1.5)),
    )


def load_rig(path):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if "layers" in data:
        layers = [
            LayerDefinition(
                name=layer["name"],
                region_polygon=(
                    [tuple(p) for p in layer["region_polygon"]]
                    if layer.get("region_polygon") else None
                ),
                joints=[_joint_from_dict(j) for j in layer.get("joints", [])],
                eyes=layer.get("eyes", []),
            )
            for layer in data["layers"]
        ]
    else:
        layers = [LayerDefinition(
            name="body", joints=[_joint_from_dict(j) for j in data["joints"]]
        )]
    remainder = [layer for layer in layers if layer.region_polygon is None]
    if len(remainder) != 1:
        raise ValueError("Debe haber exactamente una capa sin region_polygon")
    names = [j.name for layer in layers for j in layer.joints]
    if len(names) != len(set(names)):
        raise ValueError("Nombres de articulación duplicados")
    return RigDefinition(
        name=data["name"],
        source=Path(data["source"]).expanduser(),
        layers=layers,
        breath_base_y=data.get("breath_base_y"),
        breath_top_y=data.get("breath_top_y"),
        notes=data.get("notes", ""),
    )


def _polygons(shape):
    """Accept one polygon [[x, y], ...] or a union [[[x, y], ...], ...]."""
    if shape and isinstance(shape[0][0], (list, tuple)):
        return [list(map(tuple, poly)) for poly in shape]
    return [list(map(tuple, shape))]


def polygon_mask(size, polygon, scale=1.0):
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for poly in _polygons(polygon):
        draw.polygon([(x * scale, y * scale) for x, y in poly], fill=255)
    return np.asarray(mask, dtype=np.float32) / 255.0 > 0.5


def build_weight_field(rigid, anchor, sigma):
    """Smooth field: 1 on `rigid`, 0 on `anchor`, C1-ish blend in between."""
    if (rigid & anchor).any():
        raise ValueError("Las regiones rígida y anclada se solapan")
    # Blur would pull values inside the regions away from 1/0, and forcing them
    # back afterwards creates a jump (a visible tear). Grow both regions by the
    # blur reach first so the blurred field already equals 1/0 inside them.
    reach = int(np.ceil(3.0 * sigma)) if sigma > 0 else 0
    grown_rigid, grown_anchor = rigid, anchor
    if reach:
        grown_rigid = ndi.distance_transform_edt(~rigid) <= reach
        grown_anchor = (ndi.distance_transform_edt(~anchor) <= reach) & ~grown_rigid
    dist_rigid = ndi.distance_transform_edt(~grown_rigid)
    dist_anchor = ndi.distance_transform_edt(~grown_anchor)
    t = dist_anchor / np.maximum(dist_anchor + dist_rigid, 1e-6)
    weight = t * t * (3.0 - 2.0 * t)
    if sigma > 0:
        weight = ndi.gaussian_filter(weight, sigma)
    weight[rigid] = 1.0
    weight[anchor] = 0.0
    return weight.astype(np.float32)


def max_boundary_jump(weight, rigid, anchor, opaque=None):
    """Largest weight step across a region boundary (should be ~0).

    Pass `opaque` to ignore transparent pixels, where a jump is invisible
    (e.g. a narrow background gap between an ear and the tail).
    """
    ring_rigid = ndi.binary_dilation(rigid) & ~rigid
    ring_anchor = ndi.binary_dilation(anchor) & ~anchor
    if opaque is not None:
        ring_rigid &= opaque
        ring_anchor &= opaque
    jumps = [0.0]
    if ring_rigid.any():
        jumps.append(float((1.0 - weight[ring_rigid]).max()))
    if ring_anchor.any():
        jumps.append(float(weight[ring_anchor].max()))
    return max(jumps)


def _prepare_joint(jd, size, scale):
    rigid = polygon_mask(size, jd.rigid_polygon, scale)
    anchor = polygon_mask(size, jd.anchor_polygon, scale)
    weight = build_weight_field(rigid, anchor, jd.smoothing_sigma * scale)
    overlay = None
    if jd.overlay:
        overlay = rigid.astype(np.float32)
        feather = jd.overlay_feather * scale
        if feather > 0:
            overlay = ndi.gaussian_filter(overlay, feather)
            # Keep the soft edge inside the rigid region (where w == 1),
            # so the overlay never disagrees with the bent layer below it.
            overlay = np.where(
                ndi.binary_erosion(rigid, iterations=max(1, round(2 * feather))),
                1.0, overlay * rigid
            ).astype(np.float32)
    return Joint(
        name=jd.name,
        pivot=(jd.pivot[0] * scale, jd.pivot[1] * scale),
        weight=weight,
        overlay_alpha=overlay,
        max_angle=jd.max_angle,
    )


def paste_accessories(image, accessories):
    """Paint scene accessories (e.g. a toy in the mouth) onto the source art.

    Pasted in source pixels before rigging, so an accessory inside the head's
    rigid region moves exactly with the head.
    """
    from .props import draw_bone_toy  # local: props depends on nothing here

    drawers = {"bone": lambda a: draw_bone_toy(a["length"], a.get("angle", 0.0))}
    for accessory in accessories or []:
        art = drawers[accessory["kind"]](accessory)
        cx, cy = accessory["center"]
        image.alpha_composite(art, (round(cx - art.width / 2), round(cy - art.height / 2)))
    return image


def prepare_rig(definition, scale=1.0, accessories=None):
    """Scale the source once (LANCZOS) and build masks/fields at that size."""
    if scale <= 0:
        raise ValueError("La escala debe ser positiva")
    image = paste_accessories(definition.load_image(), accessories)
    if scale != 1.0:
        image = image.resize(
            (max(1, round(image.width * scale)),
             max(1, round(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
    rgba = np.array(image, dtype=np.float32) / 255.0
    alpha = rgba[..., 3]
    opaque = alpha > ALPHA_THRESHOLD / 255.0
    rows = np.nonzero(opaque.any(axis=1))[0]
    cols = np.nonzero(opaque.any(axis=0))[0]
    if rows.size == 0:
        raise ValueError(f"Imagen completamente transparente: {definition.source}")

    claimed = np.zeros(alpha.shape, dtype=bool)
    region_masks = {}
    for ld in definition.layers:
        if ld.region_polygon is not None:
            mask = polygon_mask(image.size, ld.region_polygon, scale) & ~claimed
            region_masks[ld.name] = mask
            claimed |= mask
    layers = []
    for ld in definition.layers:
        mask = region_masks.get(ld.name, ~claimed)
        layer_rgba = rgba * mask[..., None]
        eyes = [
            build_eye(
                rgba,
                (spec["center"][0] * scale, spec["center"][1] * scale),
                (spec["radii"][0] * scale, spec["radii"][1] * scale),
                line_width=max(1.0, spec.get("line_width", 6) * scale),
                line_rgb=np.array(spec.get("line_rgb", [38, 22, 18]), np.float32) / 255.0,
            )
            for spec in ld.eyes
        ]
        layers.append(Layer(
            name=ld.name,
            rgba=layer_rgba,
            joints=[_prepare_joint(jd, image.size, scale) for jd in ld.joints],
            eyes=eyes,
        ))

    base = definition.breath_base_y
    top = definition.breath_top_y
    return PreparedRig(
        name=definition.name,
        rgba=rgba,
        layers=layers,
        breath_base_y=(base * scale) if base is not None else float(rows[-1]),
        breath_top_y=(top * scale) if top is not None else float(rows[0]),
        base_x=float((cols[0] + cols[-1]) / 2.0),
    )
