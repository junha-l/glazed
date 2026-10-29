"""Colour conversion. Blender works in scene-linear RGBA; matplotlib and colour specs are sRGB."""

from __future__ import annotations

import numpy as np
from matplotlib import colormaps
from matplotlib.colors import to_rgb


def srgb_to_linear(c) -> np.ndarray:
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c) -> np.ndarray:
    c = np.clip(np.asarray(c, dtype=np.float64), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def parse_color(spec: str) -> tuple[float, float, float]:
    """Any matplotlib colour spec ("white", "#2b2f36", "0.8", ...) as an sRGB triple."""
    return to_rgb(spec)


def to_linear_rgba(srgb) -> np.ndarray:
    """sRGB of shape (..., 3) as opaque linear RGBA of shape (..., 4)."""
    linear = srgb_to_linear(srgb)
    return np.concatenate([linear, np.ones(linear.shape[:-1] + (1,))], axis=-1)


def colormap(values: np.ndarray, cmap: str) -> np.ndarray:
    """(N,) values in [0, 1] through a matplotlib colormap, as (N, 4) linear RGBA."""
    return to_linear_rgba(colormaps[cmap](np.clip(values, 0.0, 1.0))[:, :3])


def save_colorbar(path: str, cmap: str, vmin: float, vmax: float, label: str = "") -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colorbar import ColorbarBase
    from matplotlib.colors import Normalize

    fig, ax = plt.subplots(figsize=(3.4, 0.42))
    bar = ColorbarBase(ax, cmap=colormaps[cmap], norm=Normalize(vmin, vmax),
                       orientation="horizontal")
    bar.set_label(label)
    bar.outline.set_linewidth(0.5)
    fig.savefig(path, dpi=300, bbox_inches="tight", transparent=True)
    plt.close(fig)
