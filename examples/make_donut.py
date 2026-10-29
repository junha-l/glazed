"""Bake the example files: a glazed donut, made with nothing but glazed.io.

    python examples/make_donut.py                      # writes the files next to this script
    glazed examples/glazed_donut.toml --gpu --elev 35   # dough + glaze meshes, RGB sprinkles
    glazed examples/donut.npy --gpu                     # a plain donut point cloud, coloured by height
"""

from pathlib import Path

import numpy as np

from glazed.io import sample_surface, save_mesh, save_points, write_scene

RING, TUBE = 0.035, 0.017  # donut radii, metres
GLAZE = 0.0025  # glaze thickness
SPRINKLE_COLORS = ["#ffffff", "#ffd23f", "#3bceac", "#ee4266", "#4d9de0", "#7b2cbf"]
HERE = Path(__file__).parent


def torus(u, v, tube):
    """Points around the z axis; u runs around the ring, v around the tube
    (0 is the outer equator, pi/2 the top)."""
    rho = RING + tube * np.cos(v)
    return np.stack([rho * np.cos(u), rho * np.sin(u), tube * np.sin(v)], axis=-1)


def quads(nu: int, nv: int, wrap_v: bool) -> np.ndarray:
    i, j = np.meshgrid(np.arange(nu), np.arange(nv if wrap_v else nv - 1), indexing="ij")
    index = lambda a, b: (a % nu) * nv + b % nv  # noqa: E731
    return np.stack([index(i, j), index(i + 1, j), index(i + 1, j + 1), index(i, j + 1)],
                    axis=-1).reshape(-1, 4)


def dough(nu=160, nv=80):
    u, v = np.meshgrid(np.linspace(0, 2 * np.pi, nu, endpoint=False),
                       np.linspace(0, 2 * np.pi, nv, endpoint=False), indexing="ij")
    return torus(u, v, TUBE).reshape(-1, 3), quads(nu, nv, wrap_v=True)


def glaze(nu=240, ns=60):
    """The top of the donut, dripping a little further down the outside in places."""
    u, s = np.meshgrid(np.linspace(0, 2 * np.pi, nu, endpoint=False), np.linspace(0, 1, ns),
                       indexing="ij")
    drips = 0.5 + 0.5 * np.sin(5 * u + 0.7 * np.sin(3 * u))
    v_outer = 0.3 - 0.55 * drips ** 3
    v_inner = np.pi + 0.25 + 0.08 * np.sin(7 * u)
    v = v_outer + s * (v_inner - v_outer)
    thickness = GLAZE * np.clip(8 * s * (1 - s), 0, 1) ** 0.5 + 1e-4  # thins out at the edges
    return torus(u, v, TUBE + thickness).reshape(-1, 3), quads(nu, ns, wrap_v=False)


def sprinkles(n=360, seed=7):
    rng = np.random.default_rng(seed)
    u = rng.uniform(0, 2 * np.pi, n)
    v = rng.uniform(0.45, np.pi - 0.1, n)  # the top, inside the glaze
    xyz = torus(u, v, TUBE + GLAZE + 0.0008)
    palette = np.array([[int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)] for c in SPRINKLE_COLORS])
    return xyz, palette[rng.integers(len(palette), size=n)]


def outward(vertices, faces):
    """Flip faces whose winding points into the tube, so smooth shading lights the outside."""
    p = vertices[faces[0]]
    normal = np.cross(p[1] - p[0], p[3] - p[0])
    ring_point = np.append(RING * p[0, :2] / np.linalg.norm(p[0, :2]), 0.0)
    return faces if normal @ (p[0] - ring_point) > 0 else faces[:, ::-1]


if __name__ == "__main__":
    dough_v, dough_f = dough()
    dough_f = outward(dough_v, dough_f)
    glaze_v, glaze_f = glaze()
    glaze_f = outward(glaze_v, glaze_f)
    sprinkle_xyz, sprinkle_rgb = sprinkles()

    save_mesh(HERE / "donut.ply", dough_v, dough_f)
    save_mesh(HERE / "glaze.ply", glaze_v, glaze_f)
    save_points(HERE / "sprinkles.npy", sprinkle_xyz, rgb=sprinkle_rgb)
    write_scene(HERE / "glazed_donut.toml", [
        {"path": HERE / "donut.ply", "color": "#d9a066"},
        {"path": HERE / "glaze.ply", "color": "#f4a6c6"},
        {"path": HERE / "sprinkles.npy", "radius": 0.0009},
    ], comment="A glazed donut: dough and glaze meshes, sprinkles as an RGB point cloud.")

    points = sample_surface(dough_v, dough_f, 60000)
    save_points(HERE / "donut.npy", points, values=points[:, 2])
    print(f"baked {', '.join(p.name for p in sorted(HERE.glob('*')) if p.suffix != '.py')}")
