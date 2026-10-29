"""The render loop: build the scene once, then render one pass per colormap."""

from __future__ import annotations

import shutil
from pathlib import Path

import bpy

from ..io import AssetSpec
from ..settings import MODES, Animation, Colormap, Lighting, RenderSettings, View
from . import color
from .camera import Pose, fit_distance, new_camera, orbit_poses, waypoint_poses
from .output import Shot, configure, encode_gif, encode_mp4
from .scene import Scene, build_scene
from .studio import build_studio

VIDEO_MODES = frozenset(MODES[1:])
OUTPUT_SUFFIXES = {".png", ".mp4", ".gif"}


def render(specs: list[AssetSpec], out: str = "outs/render", modes=("still",),
           settings: RenderSettings | None = None, lighting: Lighting | None = None,
           view: View | None = None, animation: Animation | None = None,
           colormap: Colormap | None = None, save_blend: bool = False) -> None:
    """Render `specs` to `out` plus an extension per mode: `out`.png for a still, or
    `out`.mp4 / .gif from frames in `out`_frames/ along a camera path. With several
    colormaps, each pass is named `out`_<colormap>."""
    settings, lighting = settings or RenderSettings(), lighting or Lighting()
    view, animation, colormap = view or View(), animation or Animation(), colormap or Colormap()
    video = not VIDEO_MODES.isdisjoint(modes)

    scene = build_scene(specs)
    light_rig = build_studio(scene.floor_z, lighting)
    camera = new_camera(view.lens)
    configure(settings, bit_depth=8 if video else 16)
    background = None if settings.background is None else color.parse_color(settings.background)
    poses = camera_poses(scene, view, animation, animation.frames if video else 1,
                         settings.resolution)
    shot = Shot(camera, light_rig, poses, settings.supersample, background)

    out = Path(out)
    if out.suffix.lower() in OUTPUT_SUFFIXES:
        out = out.with_suffix("")
    out.parent.mkdir(parents=True, exist_ok=True)
    vmin, vmax = (scene.value_range(colormap.vmin, colormap.vmax) if scene.has_values
                  else (0.0, 1.0))
    cmaps = colormap.names if scene.has_values else [None]
    for cmap in cmaps:
        base = f"{out}_{cmap}" if len(cmaps) > 1 else str(out)
        scene.paint(cmap, vmin, vmax)
        if colormap.colorbar and cmap:
            color.save_colorbar(f"{base}_colorbar.png", cmap, vmin, vmax, colormap.label)
        if save_blend:
            bpy.ops.wm.save_as_mainfile(filepath=str(Path(f"{base}.blend").resolve()))

        if not video:
            shot.still(f"{base}.png")
            continue
        frame_dir = f"{base}_frames"
        shot.frames(frame_dir)
        if "mp4" in modes:
            encode_mp4(frame_dir, f"{base}.mp4", animation.fps)
        if "gif" in modes:
            encode_gif(frame_dir, f"{base}.gif", animation.fps, animation.gif_width)
        if "png" not in modes and not animation.keep_frames:
            shutil.rmtree(frame_dir)
    print("[done]")


def camera_poses(scene: Scene, view: View, animation: Animation, frames: int,
                 resolution: tuple[int, int]) -> list[Pose]:
    if view.waypoints:
        return waypoint_poses(view.waypoints, frames, scene.focus)
    distance = view.distance
    if distance is None:
        distance = fit_distance(scene.points, scene.focus, view.lens, resolution)
        print(f"[i] camera distance {distance:.2f}")
    return orbit_poses(view, animation, frames, distance, scene.focus)
