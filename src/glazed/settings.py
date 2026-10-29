"""Render settings shared by the command line and the Python API. Plain data, no Blender."""

from __future__ import annotations

from dataclasses import dataclass

MODES = ("still", "png", "mp4", "gif")


@dataclass
class RenderSettings:
    resolution: tuple[int, int] = (1400, 1050)
    supersample: int = 2  # render at Nx, then box-filter down to `resolution`
    samples: int = 256
    exposure: float = 0.0  # stops
    gpu: bool = False
    background: str | None = "white"  # backdrop colour; None keeps it transparent


@dataclass
class Lighting:
    key: float = 1.0  # multiplier on the key light
    ambient: float = 1.0  # multiplier on the environment; fills the shadows
    key_azim: float = -90.0  # degrees from the camera; negative is the camera's left
    key_elev: float = 35.0  # degrees above the horizon


@dataclass
class View:
    azim: float = 45.0  # degrees; where an orbit starts
    elev: float = 22.0  # degrees
    distance: float | None = None  # multiple of the scene's half-size; None fits it in frame
    lens: float = 50.0  # mm; shorter = stronger perspective
    waypoints: str | None = None  # JSON camera path that replaces the orbit


@dataclass
class Animation:
    frames: int = 120
    fps: int = 30
    turns: float = 1.0
    elev_amp: float = 0.0  # degrees of up-down sway
    dolly: float = 0.0  # fractional push-in over the shot
    ease: bool = False  # slow in/out; breaks a seamless loop
    gif_width: int = 720
    keep_frames: bool = True


@dataclass
class Colormap:
    names: tuple[str, ...] = ("viridis",)  # one render pass per colormap
    vmin: float | None = None  # None: the data minimum
    vmax: float | None = None
    colorbar: bool = False
    label: str = ""
