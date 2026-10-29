"""Render configuration, writing images, and encoding video."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

import bpy
import numpy as np

from ..settings import RenderSettings
from .camera import Pose, aim
from .color import linear_to_srgb, srgb_to_linear

GPU_BACKENDS = ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI")
FRAME_PATTERN = "frame_%05d.png"


def configure(settings: RenderSettings, bit_depth: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = settings.samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.use_denoising = True
    scene.cycles.device = 'GPU' if settings.gpu and enable_gpu() else 'CPU'

    scene.render.resolution_x, scene.render.resolution_y = settings.resolution
    scene.render.resolution_percentage = 100 * settings.supersample
    scene.render.film_transparent = True  # the backdrop is composited in finish()
    scene.render.use_persistent_data = True
    image = scene.render.image_settings
    image.file_format, image.color_mode, image.color_depth = 'PNG', 'RGBA', str(bit_depth)

    # The default AgX view desaturates and hue-shifts, breaking the colormap.
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    scene.view_settings.exposure = settings.exposure


def enable_gpu() -> bool:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.get_devices()
    for backend in GPU_BACKENDS:
        try:
            prefs.compute_device_type = backend
        except TypeError:
            continue
        devices = [d for d in prefs.devices if d.type == backend]
        if devices:
            for d in prefs.devices:
                d.use = d.type == backend
            print(f"[i] GPU: {backend} ({', '.join(d.name for d in devices)})")
            return True
    print("[!] no GPU backend found, using the CPU")
    return False


@dataclass
class Shot:
    camera: bpy.types.Object
    light_rig: bpy.types.Object
    poses: list[Pose]
    supersample: int
    background: tuple[float, float, float] | None  # sRGB; None keeps the alpha

    def still(self, path: str) -> None:
        aim(self.camera, self.light_rig, *self.poses[0])
        self.render(path)
        print(f"[ok] {path}")

    def frames(self, out_dir: str) -> None:
        os.makedirs(out_dir, exist_ok=True)
        for i, pose in enumerate(self.poses):
            aim(self.camera, self.light_rig, *pose)
            self.render(os.path.join(out_dir, FRAME_PATTERN % i))
            print(f"[i]   frame {i + 1}/{len(self.poses)}")

    def render(self, path: str) -> None:
        bpy.context.scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        finish(path, self.supersample, self.background)


def finish(path: str, factor: int, background) -> None:
    """Box-filter a supersampled render down by `factor` and composite it onto
    `background`, in place.

    Filtering runs in linear premultiplied space, so edges don't fringe.
    Compositing runs in display space, exactly as LaTeX or a PDF viewer places a
    transparent PNG on a page; blending in linear washes the floor shadow out.
    """
    if factor == 1 and background is None:
        return
    image = bpy.data.images.load(path)
    w, h = image.size
    px = np.empty(w * h * 4, dtype=np.float32)
    image.pixels.foreach_get(px)
    px = px.reshape(h, w, 4).astype(np.float64)
    # 16-bit PNGs load as linear premultiplied floats, 8-bit as sRGB straight
    if not image.is_float:
        px[..., :3] = srgb_to_linear(px[..., :3]) * px[..., 3:]

    if factor > 1:
        h, w = h // factor, w // factor
        px = px[:h * factor, :w * factor].reshape(h, factor, w, factor, 4).mean(axis=(1, 3))
    if background is not None:
        alpha = px[..., 3:]
        srgb = linear_to_srgb(unpremultiply(px))
        px[..., :3] = srgb_to_linear(srgb * alpha + np.asarray(background) * (1.0 - alpha))
        px[..., 3] = 1.0

    if not image.is_float:
        px[..., :3] = linear_to_srgb(unpremultiply(px))
    image.scale(w, h)
    image.pixels.foreach_set(px.astype(np.float32).ravel())
    image.save()
    bpy.data.images.remove(image)


def unpremultiply(rgba: np.ndarray) -> np.ndarray:
    rgb, alpha = rgba[..., :3], rgba[..., 3:]
    return np.divide(rgb, alpha, out=np.zeros_like(rgb), where=alpha > 0)


def encode_mp4(frame_dir: str, path: str, fps: int, crf: int = 18) -> None:
    if not shutil.which("ffmpeg"):
        print("[!] ffmpeg not found, skipping mp4")
        return
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
        "-i", os.path.join(frame_dir, FRAME_PATTERN),
        "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # yuv420p needs even dimensions
        "-movflags", "+faststart", path,
    ], check=True)
    print(f"[ok] {path}")


def encode_gif(frame_dir: str, path: str, fps: int, width: int = 720) -> None:
    """Two-pass palette GIF: smooth colormap gradients band badly in 256 colours
    without diff-based palette stats and dithering."""
    if shutil.which("ffmpeg"):
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
            "-i", os.path.join(frame_dir, FRAME_PATTERN),
            "-filter_complex",
            f"fps={fps},scale={width}:-1:flags=lanczos,split[a][b];"
            "[a]palettegen=max_colors=256:stats_mode=diff[p];"
            "[b][p]paletteuse=dither=bayer:bayer_scale=3",
            "-loop", "0", path,
        ], check=True)
        print(f"[ok] {path}")
        return

    from PIL import Image
    frames = []
    for name in sorted(f for f in os.listdir(frame_dir) if f.endswith(".png")):
        frame = Image.open(os.path.join(frame_dir, name)).convert("RGB")
        if frame.width > width:
            frame = frame.resize((width, round(frame.height * width / frame.width)), Image.LANCZOS)
        frames.append(frame.convert("P", palette=Image.ADAPTIVE, colors=256))
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=round(1000 / fps), loop=0, optimize=True)
    print(f"[ok] {path} (Pillow fallback; ffmpeg gives better quality)")
