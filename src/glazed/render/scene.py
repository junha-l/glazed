"""All assets under one root, normalised to a common frame."""

from __future__ import annotations

from dataclasses import dataclass

import bpy
import numpy as np
from mathutils import Matrix

from ..io import AssetSpec
from .assets import Asset, load_asset
from .blender import new_object, reset


@dataclass
class Scene:
    """Assets normalised so the scene's bounding box is centred on the origin with
    a largest half-side of 1. Lighting, floor and framing all work in these units,
    which keeps them independent of the data's scale."""
    assets: list[Asset]
    points: np.ndarray  # every point and vertex, normalised

    @property
    def floor_z(self) -> float:
        return float(self.points[:, 2].min())

    @property
    def focus(self) -> np.ndarray:
        return np.array([0.0, 0.0, self.floor_z + 0.5])

    @property
    def has_values(self) -> bool:
        return any(asset.values is not None for asset in self.assets)

    def value_range(self, vmin: float | None = None,
                    vmax: float | None = None) -> tuple[float, float]:
        """Shared colormap range across assets; data min/max fill in the Nones."""
        values = np.concatenate([a.values for a in self.assets if a.values is not None])
        return (float(values.min()) if vmin is None else vmin,
                float(values.max()) if vmax is None else vmax)

    def paint(self, cmap: str | None, vmin: float, vmax: float) -> None:
        for asset in self.assets:
            asset.paint(cmap, vmin, vmax)


def build_scene(specs: list[AssetSpec]) -> Scene:
    reset()
    root = new_object("scene")
    assets = [load_asset(spec, root) for spec in specs]
    bpy.context.view_layer.update()

    points = np.concatenate([asset.world_points() for asset in assets])
    center = (points.min(axis=0) + points.max(axis=0)) / 2
    scale = 1.0 / np.abs(points - center).max()
    root.matrix_world = Matrix.Scale(scale, 4) @ Matrix.Translation(-center)
    return Scene(assets, (points - center) * scale)
