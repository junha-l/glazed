"""USD files for the preview, read by Blender's importer exactly as a render reads them.

Browsers can't read USD's binary crate format, so the preview server imports the
files here and hands the page plain arrays: each mesh's triangles, where it is on
every frame, and its vertices on every frame when the mesh itself deforms.
"""

from __future__ import annotations

from dataclasses import dataclass

import bpy
import numpy as np

from .assets import import_file, is_animated
from .blender import reset, world_corners

NO_MATERIAL = (0.8, 0.8, 0.8)  # what Cycles shows for a mesh without a material


@dataclass
class Part:
    """One mesh of a USD file, in the file's own units after Blender's axis conversion."""
    name: str
    color: tuple[float, float, float]  # linear RGB of its material, for --color original
    triangles: np.ndarray  # (T, 3) uint32
    positions: np.ndarray  # (F, V, 3) float32: every frame when it deforms, else one
    matrices: np.ndarray  # (F, 4, 4) float32 object-to-file transforms per frame, row-major


@dataclass
class UsdFile:
    parts: list[Part]
    corners: np.ndarray  # (K, 3) parts' bounding box corners after the first frame, as
                         # scene.build_scene adds them, so the preview frames the same way


def load_usd(paths: list[str], every: int) -> tuple[list[int], list[UsdFile]]:
    """The frames a video would play (empty when nothing moves) and each file's meshes.

    The files share one Blender scene, as in a render, so the last one imported
    sets the frame range."""
    reset()
    imported = [import_file(path) for path in paths]
    animated = [any(is_animated(obj) for obj in objects) for objects in imported]
    meshes = [[obj for obj in objects if obj.type == 'MESH'] for objects in imported]
    timeline = bpy.context.scene
    frames = (list(range(timeline.frame_start, timeline.frame_end + 1, every))
              if any(animated) else [])

    depsgraph = bpy.context.evaluated_depsgraph_get()
    triangles, matrices, positions = {}, {}, {}
    corners = [[] for _ in paths]
    for i, frame in enumerate(frames or [timeline.frame_current]):
        timeline.frame_set(frame)
        for objects, moving, file_corners in zip(meshes, animated, corners):
            for obj in objects:
                matrices.setdefault(obj, []).append(np.array(obj.matrix_world, dtype=np.float32))
                if i == 0:
                    triangles[obj], first = evaluated_mesh(obj, depsgraph)
                    positions[obj] = [first]
                elif moving and obj.modifiers:  # a mesh cache or a skeleton deforms it
                    positions[obj].append(evaluated_mesh(obj, depsgraph)[1])
                if i > 0 and moving:
                    file_corners.append(world_corners(obj))

    files = [UsdFile([Part(obj.name, material_color(obj), triangles[obj],
                           steady(obj.name, positions[obj]), np.stack(matrices[obj]))
                      for obj in objects],
                     np.concatenate(file_corners or [np.empty((0, 3))]))
             for objects, file_corners in zip(meshes, corners)]
    if frames:
        timeline.frame_set(frames[0])
    return frames, files


def evaluated_mesh(obj: bpy.types.Object, depsgraph) -> tuple[np.ndarray, np.ndarray]:
    """(T, 3) triangle vertex indices and (V, 3) vertices, after modifiers."""
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
        mesh.vertices.foreach_get("co", co)
        mesh.calc_loop_triangles()
        indices = np.empty(len(mesh.loop_triangles) * 3, dtype=np.uint32)
        mesh.loop_triangles.foreach_get("vertices", indices)
    finally:
        evaluated.to_mesh_clear()
    return indices.reshape(-1, 3), co.reshape(-1, 3)


def steady(name: str, positions: list[np.ndarray]) -> np.ndarray:
    """Every frame's vertices, or just the first when they never move or the vertex
    count changes, which the preview can't follow."""
    if any(len(p) != len(positions[0]) for p in positions):
        print(f"[!] {name}: its vertex count changes over time; the preview shows it unmoving")
        return positions[0][None]
    stacked = np.stack(positions)
    return stacked[:1] if (stacked == stacked[0]).all() else stacked


def material_color(obj: bpy.types.Object) -> tuple[float, float, float]:
    """The importer stores USD's display colour as the material's viewport colour."""
    material = obj.active_material
    return tuple(material.diffuse_color[:3]) if material else NO_MATERIAL
