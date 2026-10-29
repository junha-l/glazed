"""The studio: one soft key light, a white environment, and a shadow-catcher floor.

Calibrated for a normalised scene (see scene.py): at exposure 0 a white surface
facing the key peaks just below clipping.
"""

from __future__ import annotations

import bpy

from ..settings import Lighting
from .blender import new_object
from .geometry import look_at, spherical

KEY_POWER = 190.0
KEY_SIZE = 4.0
KEY_DISTANCE = 5.0
AMBIENT_STRENGTH = 0.15
FLOOR_SIZE = 20.0


def build_studio(floor_z: float, lighting: Lighting) -> bpy.types.Object:
    """Build the studio and return the light rig, which camera.aim spins with
    the camera so the key keeps its angle to the view.

    A side light shades each surface across its width, which is what reads as
    depth; light from near the camera flattens the shape.
    """
    world = bpy.data.worlds.new("studio")
    background = world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    background.inputs["Strength"].default_value = AMBIENT_STRENGTH * lighting.ambient
    bpy.context.scene.world = world

    rig = new_object("light_rig")
    key = new_object("key", bpy.data.lights.new("key", 'AREA'), parent=rig)
    key.data.size = KEY_SIZE
    key.data.energy = KEY_POWER * lighting.key
    eye = spherical(KEY_DISTANCE, lighting.key_azim, lighting.key_elev) + (0.0, 0.0, floor_z)
    key.matrix_world = look_at(eye, (0.0, 0.0, floor_z + 0.4))

    bpy.ops.mesh.primitive_plane_add(size=FLOOR_SIZE, location=(0.0, 0.0, floor_z))
    bpy.context.active_object.is_shadow_catcher = True
    return rig
