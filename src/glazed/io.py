"""The glazed scene format: write point clouds, meshes, and scene files, and read them back.

Needs only numpy (plus tomli before Python 3.11), so it installs into any research
environment with `pip install glazed`. Rendering the files is glazed.render's job,
which needs Blender's bpy. Every function here accepts numpy arrays, lists, or
torch tensors on any device.
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib

POINT_CLOUD_SUFFIXES = (".npy",)
MESH_SUFFIXES = (".obj", ".ply", ".stl", ".glb", ".gltf", ".fbx")
SCENE_SUFFIXES = (".toml", ".json")
RADIUS_PER_SPACING = 1.2  # closes most gaps in randomly sampled clouds without merging points


@dataclass
class AssetSpec:
    """One file in a scene. The transform is in the file's own units, applied before
    the whole scene is normalised for rendering."""
    path: str
    color: str = "#cccccc"  # for anything without per-point values; "original" keeps mesh materials
    location: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)  # XYZ degrees, about the file's origin
    scale: float = 1.0
    radius: float | None = None  # point clouds; None picks one from the point spacing
    radius_scale: float = 1.0
    smooth: bool = True  # meshes: smooth shading


SCENE_KEYS = tuple(field.name for field in dataclasses.fields(AssetSpec))

# Rotations taking the named axis to +z, glazed's up axis.
_TO_Z_UP = {
    "z": lambda p: p,
    "-z": lambda p: np.stack([p[:, 0], -p[:, 1], -p[:, 2]], axis=1),
    "y": lambda p: np.stack([p[:, 0], -p[:, 2], p[:, 1]], axis=1),
    "-y": lambda p: np.stack([p[:, 0], p[:, 2], -p[:, 1]], axis=1),
    "x": lambda p: np.stack([-p[:, 2], p[:, 1], p[:, 0]], axis=1),
    "-x": lambda p: np.stack([p[:, 2], p[:, 1], -p[:, 0]], axis=1),
}


def as_numpy(x) -> np.ndarray:
    if hasattr(x, "detach"):
        x = x.detach().cpu().numpy()
    return np.asarray(x)


def save_points(path, xyz, values=None, rgb=None) -> str:
    """Point cloud as .npy: (N, 3) xyz; with `values`, (N, 4) coloured through the
    colormap; with `rgb` in [0, 1], (N, 6) coloured as given."""
    if values is not None and rgb is not None:
        raise ValueError("pass values or rgb, not both")
    columns = [as_numpy(xyz).reshape(-1, 3)]
    if values is not None:
        columns.append(as_numpy(values).reshape(-1, 1))
    if rgb is not None:
        columns.append(as_numpy(rgb).reshape(-1, 3))
    data = np.concatenate(columns, axis=1).astype(np.float32)
    _require_finite(path, data)
    np.save(path, data)
    return str(path)


def save_mesh(path, vertices, faces) -> str:
    """Triangle or quad mesh as binary PLY, which Blender reads with coordinates as
    stored. Prefer it to OBJ, which Blender's importer rotates from Y-up to Z-up."""
    v = as_numpy(vertices).reshape(-1, 3).astype("<f4")
    f = as_numpy(faces).astype(np.int64)
    if f.ndim != 2 or f.shape[1] not in (3, 4):
        raise ValueError(f"{path}: faces must be (F, 3) or (F, 4), got {f.shape}")
    if f.min() < 0 or f.max() >= len(v):
        raise ValueError(f"{path}: face indices out of range for {len(v)} vertices")
    _require_finite(path, v)

    records = np.empty(len(f), dtype=[("n", "u1"), ("idx", "<i4", (f.shape[1],))])
    records["n"] = f.shape[1]
    records["idx"] = f
    header = ("ply\nformat binary_little_endian 1.0\n"
              f"element vertex {len(v)}\nproperty float x\nproperty float y\nproperty float z\n"
              f"element face {len(f)}\nproperty list uchar int vertex_indices\nend_header\n")
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(v.tobytes())
        fh.write(records.tobytes())
    return str(path)


def sample_surface(vertices, faces, n: int, seed: int = 0) -> np.ndarray:
    """(n, 3) points spread uniformly over a mesh's surface."""
    v = as_numpy(vertices).reshape(-1, 3).astype(np.float64)
    f = as_numpy(faces).astype(np.int64)
    if f.shape[1] == 4:
        f = np.concatenate([f[:, [0, 1, 2]], f[:, [0, 2, 3]]])
    tri = v[f]
    area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    rng = np.random.default_rng(seed)
    picked = tri[rng.choice(len(tri), n, p=area / area.sum())]
    r1, r2 = rng.random((2, n, 1))
    s = np.sqrt(r1)
    return (1 - s) * picked[:, 0] + s * (1 - r2) * picked[:, 1] + s * r2 * picked[:, 2]


def to_z_up(xyz, up: str = "y") -> np.ndarray:
    """Rotate points so the `up` axis ("y", "-y", "x", "-x", "z", "-z") becomes +z.
    Apply the same call to every array in a scene so its parts stay aligned."""
    return _TO_Z_UP[up](as_numpy(xyz).reshape(-1, 3))


def point_radius(xyz, radius: float | None = None, radius_scale: float = 1.0) -> float:
    """The sphere radius glazed renders a cloud's points with, in file units: `radius`
    if given, otherwise one picked from the point spacing, times `radius_scale`."""
    if radius:
        return radius
    return RADIUS_PER_SPACING * median_spacing(as_numpy(xyz).reshape(-1, 3)) * radius_scale


def median_spacing(points: np.ndarray, n_query: int = 2000, n_ref: int = 20000,
                   seed: int = 0) -> float:
    """Median nearest-neighbour distance, estimated on a subsample."""
    rng = np.random.default_rng(seed)
    n = len(points)
    query = points[rng.choice(n, min(n_query, n), replace=False)]
    ref = points[rng.choice(n, min(n_ref, n), replace=False)]
    nearest = np.full(len(query), np.inf)
    for i in range(0, len(ref), 4096):
        d = np.linalg.norm(query[:, None, :] - ref[None, i:i + 4096, :], axis=2)
        d[d < 1e-12] = np.inf
        nearest = np.minimum(nearest, d.min(axis=1))
    finite = nearest[np.isfinite(nearest)]
    return float(np.median(finite)) if finite.size else 1e-3


def check_alignment(a, b, names: tuple[str, str] = ("a", "b")) -> dict:
    """Print the sizes of two point sets and the closest distance between them.

    Catches unit mix-ups (sizes ~1000x apart: mm vs m) and parts exported in
    different frames (a gap far larger than expected), which glazed can't detect:
    it never moves one file relative to another. For meshes pass sample_surface()
    points; raw vertices of large faces overstate the gap.
    """
    a = as_numpy(a).reshape(-1, 3).astype(np.float64)
    b = as_numpy(b).reshape(-1, 3).astype(np.float64)
    rng = np.random.default_rng(0)
    query = a[rng.choice(len(a), min(len(a), 2000), replace=False)]
    ref = b[rng.choice(len(b), min(len(b), 20000), replace=False)]
    gap = min(np.linalg.norm(query[:, None] - ref[None, i:i + 2048], axis=2).min()
              for i in range(0, len(ref), 2048))
    report = {
        f"{names[0]}_size": float(np.linalg.norm(np.ptp(a, axis=0))),
        f"{names[1]}_size": float(np.linalg.norm(np.ptp(b, axis=0))),
        "gap": float(gap),
        "center_distance": float(np.linalg.norm(a.mean(0) - b.mean(0))),
    }
    print("[check_alignment] " + ", ".join(f"{k} {v:.4g}" for k, v in report.items()))
    return report


def grid_locations(count: int, spacing: float, columns: int | None = None) -> list:
    """[x, y, 0] offsets laying `count` groups out in rows `spacing` apart. Give every
    file of one group (e.g. a hand and its object) the same location."""
    columns = columns or math.ceil(math.sqrt(count))
    return [[(i % columns) * spacing, -(i // columns) * spacing, 0.0] for i in range(count)]


def write_scene(path, objects: list, comment: str | None = None) -> str:
    """Write a scene .toml from AssetSpecs or dicts of AssetSpec fields. Paths may be
    absolute; they are stored relative to the scene file."""
    path = Path(path)
    lines = [f"# {comment}"] if comment else []
    for obj in objects:
        entry = _entry(obj)
        lines += ["", "[[objects]]"]
        for key in SCENE_KEYS:
            if key in entry:
                value = entry[key]
                if key == "path":
                    relative = os.path.relpath(Path(value).resolve(), path.parent.resolve())
                    value = Path(relative).as_posix()
                lines.append(f"{key} = {_toml_value(value)}")
    text = "\n".join(lines).lstrip("\n") + "\n"
    tomllib.loads(text)
    path.write_text(text)
    return str(path)


def read_scene(path, defaults: dict | None = None) -> list[AssetSpec]:
    """AssetSpecs from a .toml or .json scene file. `defaults` fill keys an entry
    leaves out; entry paths resolve relative to the scene file."""
    path = Path(path)
    parse = tomllib.loads if path.suffix.lower() == ".toml" else json.loads
    data = parse(path.read_text())
    if not isinstance(data, dict) or "objects" not in data:
        raise ValueError(f"{path}: not a scene file (no 'objects' list)")
    specs = []
    for entry in data["objects"]:
        entry = {**(defaults or {}), **entry}
        entry["path"] = str(path.parent / entry["path"])
        specs.append(AssetSpec(**entry))
    return specs


def read_inputs(paths, defaults: dict | None = None) -> list[AssetSpec]:
    """AssetSpecs from any mix of asset files and scene files."""
    specs = []
    for path in map(Path, paths):
        if path.suffix.lower() in SCENE_SUFFIXES:
            specs += read_scene(path, defaults)
        else:
            specs.append(AssetSpec(str(path), **(defaults or {})))
    for spec in specs:
        if Path(spec.path).suffix.lower() not in POINT_CLOUD_SUFFIXES + MESH_SUFFIXES:
            supported = " ".join(POINT_CLOUD_SUFFIXES + MESH_SUFFIXES + SCENE_SUFFIXES)
            raise ValueError(f"{spec.path}: unsupported file type, expected one of {supported}")
    return specs


def check_scene(path) -> list[str]:
    """Problems glazed would hit rendering a scene file, found without rendering:
    missing or unsupported files, malformed point arrays, and a caution when OBJ
    is mixed with other formats. Returns an empty list when the scene is fine."""
    specs = read_scene(path)
    problems = []
    for spec in specs:
        file = Path(spec.path)
        if not file.exists():
            problems.append(f"{file}: missing")
        elif file.suffix.lower() not in POINT_CLOUD_SUFFIXES + MESH_SUFFIXES:
            problems.append(f"{file}: unsupported file type")
        elif file.suffix.lower() in POINT_CLOUD_SUFFIXES:
            data = np.load(file, mmap_mode="r")
            if data.ndim != 2 or data.shape[1] not in (3, 4, 6):
                problems.append(f"{file}: expected an (N, 3|4|6) array, got {data.shape}")
            elif not np.isfinite(data).all():
                problems.append(f"{file}: contains NaN or inf")
    suffixes = {Path(spec.path).suffix.lower() for spec in specs}
    if ".obj" in suffixes and len(suffixes) > 1:
        problems.append("caution: OBJ files are read as Y-up and rotated to Z-up, while the "
                        "other formats are read as stored. Fine for standard Y-up OBJ files; an "
                        "OBJ written in the other files' Z-up frame will be tilted 90 degrees. "
                        "save_mesh writes PLY, which avoids the question")
    return problems


def _entry(obj) -> dict:
    if isinstance(obj, AssetSpec):
        defaults = AssetSpec(obj.path)
        return {key: value for key, value in dataclasses.asdict(obj).items()
                if key == "path" or value != getattr(defaults, key)}
    unknown = set(obj) - set(SCENE_KEYS)
    if unknown or "path" not in obj:
        raise ValueError(f"scene entries need 'path' and only {SCENE_KEYS}; got {sorted(obj)}")
    return obj


def _toml_value(value) -> str:
    if isinstance(value, (bool, np.bool_)):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (list, tuple, np.ndarray)) or hasattr(value, "detach"):
        return "[" + ", ".join(_toml_value(v) for v in as_numpy(value).tolist()) + "]"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite number in scene: {value}")
    return repr(number)


def _require_finite(path, data: np.ndarray) -> None:
    if not np.isfinite(data).all():
        raise ValueError(f"{path}: contains NaN or inf")
