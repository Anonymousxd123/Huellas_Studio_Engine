"""Deterministic 2D character animation for Huellas Studio.

Characters are single painted images, not articulated puppets. Instead of
cutting a head out and rotating it over a hole, the engine bends the image
with a smooth weight field (1 on the head, 0 on the anchored body/collar),
then composites the rigidly transformed head on top so it can occlude the
collar where it swings down. The rest pose reproduces the source exactly.
"""

from .deform import Joint, PreparedRig, render_pose
from .motion import Track, sample_tracks
from .rig import RigDefinition, load_rig, prepare_rig

__all__ = [
    "Joint",
    "PreparedRig",
    "RigDefinition",
    "Track",
    "load_rig",
    "prepare_rig",
    "render_pose",
    "sample_tracks",
]
