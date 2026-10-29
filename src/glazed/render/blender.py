"""Small bpy helpers shared by the scene builders."""

from __future__ import annotations

import bpy
import numpy as np

COLOR_ATTRIBUTE = "studio_color"


def reset() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def new_object(name: str, data=None, parent=None) -> bpy.types.Object:
    """A new object linked into the scene; with no data it is an empty."""
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    return obj


def world_vertices(obj: bpy.types.Object) -> np.ndarray:
    """(N, 3) world positions of a mesh's vertices or a point cloud's points."""
    if obj.type == 'MESH':
        items, key = obj.data.vertices, "co"
    else:
        items, key = obj.data.attributes["position"].data, "vector"
    local = np.empty(len(items) * 3, dtype=np.float32)
    items.foreach_get(key, local)
    matrix = np.array(obj.matrix_world)
    return local.reshape(-1, 3) @ matrix[:3, :3].T + matrix[:3, 3]


def write_colors(obj: bpy.types.Object, rgba) -> None:
    """Write linear RGBA, one (4,) colour or (N, 4), to the per-point colour attribute."""
    attributes = obj.data.attributes
    attribute = (attributes.get(COLOR_ATTRIBUTE)
                 or attributes.new(COLOR_ATTRIBUTE, 'FLOAT_COLOR', 'POINT'))
    rgba = np.broadcast_to(np.asarray(rgba, dtype=np.float32), (len(attribute.data), 4))
    attribute.data.foreach_set("color", rgba.ravel())
    obj.data.update_tag()
