"""Input files loaded into the Blender scene as colourable assets.

Each file becomes an Asset: an empty (the anchor) carrying the spec's transform,
with the renderable objects parented under it. To support a new file type, list
its suffix in glazed.io and map it to a Blender importer in IMPORTERS, or to an
Asset subclass in LOADERS.
"""

from __future__ import annotations

from pathlib import Path

import bpy
import numpy as np

from ..io import AssetSpec, point_radius
from . import color
from .blender import COLOR_ATTRIBUTE, new_object, world_vertices, write_colors

IMPORTERS = {
    ".obj": bpy.ops.wm.obj_import,
    ".ply": bpy.ops.wm.ply_import,
    ".stl": bpy.ops.wm.stl_import,
    ".glb": bpy.ops.import_scene.gltf,
    ".gltf": bpy.ops.import_scene.gltf,
    ".fbx": bpy.ops.import_scene.fbx,
}


class Asset:
    values: np.ndarray | None = None  # per-point scalars, coloured through the colormap

    def __init__(self, spec: AssetSpec, parent: bpy.types.Object):
        self.spec = spec
        self.anchor = new_object(Path(spec.path).stem, parent=parent)
        self.anchor.location = spec.location
        self.anchor.rotation_euler = np.radians(spec.rotation)
        self.anchor.scale = (spec.scale,) * 3
        self.objects: list[bpy.types.Object] = []

    def world_points(self) -> np.ndarray:
        return np.concatenate([world_vertices(obj) for obj in self.objects])

    def paint(self, cmap: str | None, vmin: float, vmax: float) -> None:
        rgba = color.to_linear_rgba(color.parse_color(self.spec.color))
        for obj in self.objects:
            write_colors(obj, rgba)


class PointCloud(Asset):
    """An .npy of shape (N, 3) xyz, (N, 4) xyz + value, or (N, 6) xyz + RGB."""

    def __init__(self, spec: AssetSpec, parent: bpy.types.Object):
        super().__init__(spec, parent)
        data = np.load(spec.path).astype(np.float64)
        if data.ndim != 2 or data.shape[1] not in (3, 4, 6):
            raise ValueError(f"{spec.path}: expected an (N, 3|4|6) array, got {data.shape}")
        xyz, extra = data[:, :3], data[:, 3:]
        self.values = extra[:, 0] if extra.shape[1] == 1 else None
        self.rgb = extra / (255.0 if extra.max() > 1.0 else 1.0) if extra.shape[1] == 3 else None

        radius = point_radius(xyz, spec.radius, spec.radius_scale)
        cloud = new_point_cloud(self.anchor.name, xyz, radius, self.anchor)
        cloud.data.materials.append(matte_material())
        self.objects = [cloud]
        print(f"[i] {spec.path}: {len(xyz)} points, radius {radius:.4g}")

    def paint(self, cmap: str | None, vmin: float, vmax: float) -> None:
        if self.values is not None:
            span = max(vmax - vmin, 1e-12)
            write_colors(self.objects[0], color.colormap((self.values - vmin) / span, cmap))
        elif self.rgb is not None:
            write_colors(self.objects[0], color.to_linear_rgba(self.rgb))
        else:
            super().paint(cmap, vmin, vmax)


class Mesh(Asset):
    """Any file type in IMPORTERS. Cameras and lights inside the file are dropped."""

    def __init__(self, spec: AssetSpec, parent: bpy.types.Object):
        super().__init__(spec, parent)
        imported = import_file(spec.path)
        for obj in imported:
            if obj.parent is None:
                obj.parent = self.anchor
        self.objects = [obj for obj in imported if obj.type == 'MESH']
        for obj in self.objects:
            if spec.smooth:
                obj.data.shade_smooth()
            if spec.color != "original":
                obj.data.materials.clear()
                obj.data.materials.append(matte_material())
        n_verts = sum(len(obj.data.vertices) for obj in self.objects)
        print(f"[i] {spec.path}: {len(self.objects)} mesh(es), {n_verts} vertices")

    def paint(self, cmap: str | None, vmin: float, vmax: float) -> None:
        if self.spec.color != "original":
            super().paint(cmap, vmin, vmax)


LOADERS: dict[str, type[Asset]] = {".npy": PointCloud, **dict.fromkeys(IMPORTERS, Mesh)}


def load_asset(spec: AssetSpec, parent: bpy.types.Object) -> Asset:
    suffix = Path(spec.path).suffix.lower()
    if suffix not in LOADERS:
        raise ValueError(f"{spec.path}: unsupported file type, expected {', '.join(LOADERS)}")
    return LOADERS[suffix](spec, parent)


def import_file(path: str) -> list[bpy.types.Object]:
    before = set(bpy.data.objects)
    IMPORTERS[Path(path).suffix.lower()](filepath=str(Path(path).resolve()))
    for obj in [obj for obj in bpy.data.objects if obj not in before]:
        if obj.type in {'CAMERA', 'LIGHT'}:
            bpy.data.objects.remove(obj)
    return [obj for obj in bpy.data.objects if obj not in before]


def new_point_cloud(name: str, xyz: np.ndarray, radius: float,
                    parent: bpy.types.Object) -> bpy.types.Object:
    """A native PointCloud, which Cycles renders directly as spheres."""
    cloud = bpy.data.pointclouds.new(name)
    cloud.resize(len(xyz))
    cloud.attributes["position"].data.foreach_set("vector", xyz.astype(np.float32).ravel())
    cloud.attributes.new("radius", 'FLOAT', 'POINT').data.foreach_set(
        "value", np.full(len(xyz), radius, dtype=np.float32))
    return new_object(name, cloud, parent)


def matte_material() -> bpy.types.Material:
    """Diffuse, coloured by the per-point colour attribute that paint() writes.

    Specular is off: highlights on thousands of tiny spheres read as noise and
    wash out the colormap.
    """
    if material := bpy.data.materials.get("matte"):
        return material
    material = bpy.data.materials.new("matte")
    nodes = material.node_tree.nodes
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.45
    bsdf.inputs["Specular IOR Level"].default_value = 0.0
    attribute = nodes.new("ShaderNodeAttribute")
    attribute.attribute_name = COLOR_ATTRIBUTE
    material.node_tree.links.new(attribute.outputs["Color"], bsdf.inputs["Base Color"])
    return material
