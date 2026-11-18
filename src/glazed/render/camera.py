"""Camera paths and framing. A pose is an (eye, target) pair in normalised scene units."""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

from ..settings import Animation, View
from .blender import new_object, world_vertices
from .geometry import catmull_rom, look_at, smootherstep, spherical
from .scene import Scene

SENSOR_WIDTH = 36.0  # Blender's default, spanning the longer image side
BEST_VIEW_STEP = 15.0  # degrees between the azimuths best_azim tries
BEST_VIEW_POINTS = 50  # surface points tested per part and frame
BEST_VIEW_FRAMES = 5  # frames of an animation tested

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


def best_azim(scene: Scene, view: View, distance: float) -> float:
    """The azimuth, in steps from view.azim, that hides the least of the scene: the one
    that sees the largest share of each part (each mesh in a file, each point cloud),
    averaged over the parts, so a hidden thumb counts as much as a hidden palm. A part's
    share is that of points sampled on it that a ray from the camera reaches before
    anything else. An animation is tested at a few frames; ties go to the angle nearest
    view.azim. Point clouds are tested but hide nothing, since rays only hit meshes."""
    azims = view.azim + np.arange(0.0, 360.0, BEST_VIEW_STEP)
    eyes = scene.focus + spherical(distance, azims, view.elev)
    timeline = bpy.context.scene  # the file's whole frame range, so --every doesn't matter
    frames = (np.linspace(timeline.frame_start, timeline.frame_end, BEST_VIEW_FRAMES)
              .round().astype(int).tolist() if scene.frames else [timeline.frame_current])
    parts = [obj for asset in scene.assets for obj in asset.objects]
    rng = np.random.default_rng(0)
    seen = np.zeros(len(azims))
    for frame in frames:
        timeline.frame_set(frame)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for part in parts:
            points = world_vertices(part)
            points = points[rng.choice(len(points), min(len(points), BEST_VIEW_POINTS),
                                       replace=False)]
            for i, eye in enumerate(eyes):
                seen[i] += np.mean([in_sight(depsgraph, eye, point) for point in points])
    timeline.frame_set(scene.frames[0] if scene.frames else frames[0])
    return float(azims[np.argmax(seen)] % 360.0)


def in_sight(depsgraph, eye: np.ndarray, point: np.ndarray, tolerance: float = 0.01) -> bool:
    """Whether nothing lies between `eye` and `point`, a point on a surface."""
    ray = point - eye
    length = float(np.linalg.norm(ray))
    return not bpy.context.scene.ray_cast(depsgraph, Vector(eye), Vector(ray / length),
                                          distance=length - tolerance)[0]


def fit_view(points: np.ndarray, poses: list[Pose], lens: float,
             resolution: tuple[int, int], margin: float = 1.08) -> float:
    """The closest distance from which the points stay in frame from every pose's
    direction, a tighter fit than fit_distance for a camera that doesn't go all round."""
    # tan of the half field of view, across and up; the sensor spans the longer side
    half = SENSOR_WIDTH / 2 / lens * np.array(resolution) / max(resolution)
    distance = 0.0
    for eye, target in {(tuple(eye), tuple(target)) for eye, target in poses}:
        axes = np.array(look_at(eye, target))[:3, :3]  # columns: right, up, back
        x, y, back = ((points - target) @ axes).T
        reach = np.maximum(np.abs(x) / half[0], np.abs(y) / half[1])
        distance = max(distance, float((back + margin * reach).max()))
    return distance


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
