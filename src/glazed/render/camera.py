"""Camera paths and framing. A pose is an (eye, target) pair in normalised scene units."""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
import numpy as np

from ..settings import Animation, View
from .blender import new_object
from .geometry import catmull_rom, look_at, smootherstep, spherical

SENSOR_WIDTH = 36.0  # Blender's default, spanning the longer image side

Pose = tuple[np.ndarray, np.ndarray]


def orbit_poses(view: View, animation: Animation, frames: int, distance: float,
                target: np.ndarray) -> list[Pose]:
    t = (smootherstep(np.linspace(0.0, 1.0, frames)) if animation.ease
         else np.linspace(0.0, 1.0, frames, endpoint=False))
    eyes = target + spherical(distance * (1.0 - animation.dolly * t),
                              view.azim + 360.0 * animation.turns * t,
                              view.elev + animation.elev_amp * np.sin(2 * np.pi * t))
    return [(eye, target) for eye in eyes]


def waypoint_poses(path: str, frames: int, target: np.ndarray) -> list[Pose]:
    """Spline through {"eye": [[x, y, z], ...], "target": [...], "loop": bool}."""
    spec = json.loads(Path(path).read_text())
    loop = spec.get("loop", False)
    eyes = catmull_rom(np.array(spec["eye"], dtype=float), frames, loop)
    targets = (catmull_rom(np.array(spec["target"], dtype=float), frames, loop)
               if "target" in spec else np.tile(target, (frames, 1)))
    return list(zip(eyes, targets))


def fit_distance(points: np.ndarray, target: np.ndarray, lens: float,
                 resolution: tuple[int, int], margin: float = 1.08) -> float:
    """Distance at which the points' bounding sphere about `target` fills the
    narrower field of view, so nothing leaves the frame from any orbit angle."""
    radius = np.linalg.norm(points - target, axis=1).max()
    half_fov = math.atan(SENSOR_WIDTH / 2 / lens * min(resolution) / max(resolution))
    return margin * radius / math.sin(half_fov)


def new_camera(lens: float) -> bpy.types.Object:
    camera = new_object("camera", bpy.data.cameras.new("camera"))
    camera.data.lens = lens
    bpy.context.scene.camera = camera
    return camera


def aim(camera: bpy.types.Object, light_rig: bpy.types.Object, eye, target) -> None:
    """Place the camera and spin the light rig to its azimuth, so the lighting
    looks the same from every orbit angle, like a turntable under fixed lights."""
    camera.matrix_world = look_at(eye, target)
    light_rig.rotation_euler.z = math.atan2(eye[1] - target[1], eye[0] - target[0])
