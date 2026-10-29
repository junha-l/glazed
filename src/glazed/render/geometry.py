"""Geometry helpers: angles to positions, look-at matrices, splines."""

from __future__ import annotations

import numpy as np
from mathutils import Matrix, Vector


def spherical(radius, azim, elev) -> np.ndarray:
    """Cartesian points from a radius and azimuth/elevation in degrees, z up. Broadcasts."""
    a, e = np.radians(azim), np.radians(elev)
    return np.stack(np.broadcast_arrays(radius * np.cos(e) * np.cos(a),
                                        radius * np.cos(e) * np.sin(a),
                                        radius * np.sin(e)), axis=-1)


def look_at(eye, target, up=(0.0, 0.0, 1.0)) -> Matrix:
    """World matrix placing a camera or light at `eye`, facing `target`.

    Blender cameras and lights look down their local -Z axis, with +Y up.
    """
    eye, up = Vector(eye), Vector(up)
    back = eye - Vector(target)
    back = back.normalized() if back.length > 1e-9 else Vector((0.0, -1.0, 0.0))
    if abs(back.dot(up)) > 0.9995:
        up = Vector((0.0, 1.0, 0.0))
    right = up.cross(back).normalized()
    true_up = back.cross(right)
    return Matrix((
        (right.x, true_up.x, back.x, eye.x),
        (right.y, true_up.y, back.y, eye.y),
        (right.z, true_up.z, back.z, eye.z),
        (0.0, 0.0, 0.0, 1.0),
    ))


def smootherstep(t: np.ndarray) -> np.ndarray:
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def catmull_rom(points: np.ndarray, n_out: int, loop: bool = False) -> np.ndarray:
    """Uniform Catmull-Rom spline through (K, 3) control points, sampled at n_out points."""
    p = np.asarray(points, dtype=np.float64)
    if len(p) < 2:
        return np.repeat(p, n_out, axis=0)[:n_out]
    ctrl = np.concatenate([p[-1:], p, p[:1], p[1:2]] if loop else [p[:1], p, p[-1:]])

    n_seg = len(ctrl) - 3
    ts = np.linspace(0.0, n_seg, n_out, endpoint=not loop)
    seg = np.clip(ts.astype(int), 0, n_seg - 1)
    u = (ts - seg)[:, None]
    p0, p1, p2, p3 = ctrl[seg], ctrl[seg + 1], ctrl[seg + 2], ctrl[seg + 3]
    return 0.5 * (2 * p1 + (p2 - p0) * u
                  + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u ** 2
                  + (3 * p1 - p0 - 3 * p2 + p3) * u ** 3)
