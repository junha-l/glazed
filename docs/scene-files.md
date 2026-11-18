# Scene files

[← README](../README.md)

A scene is one or more files, given on the command line or laid out by a scene
file. `glazed.io` writes both from your project's own environment, with only
numpy.

## Input formats

Point clouds are `.npy` arrays of shape (N, 3) xyz, (N, 4) xyz + value, or
(N, 6) xyz + RGB. Meshes can be `.ply`, `.stl`, `.obj`, `.glb`, `.gltf`, `.fbx`, or
USD (`.usd`, `.usda`, `.usdc`, `.usdz`), which can be animated. `save_mesh` writes
PLY, which Blender reads with coordinates as stored, while OBJ files are treated as
Y-up.

## glazed.io

`save_mesh`, `save_points`, and `write_scene` write the files, as the
[README](../README.md#your-own-data) shows. Every function takes numpy arrays or
torch tensors on any device. `glazed.io` also has `sample_surface`, `to_z_up`,
`check_alignment`, `grid_locations`, `read_scene`, and `check_scene`.
`examples/make_donut.py` bakes the example donut with it.

## Keys

```toml
[[objects]]
path = "cloud.npy"
radius_scale = 1.25

[[objects]]
path = "mesh.ply"
color = "#c9ccd1"
location = [7.5, 0, 0]   # in the file's own units
rotation = [0, 0, 90]    # degrees about x, y, z
```

| Key | Default | |
|---|---|---|
| `path` | required | relative to the scene file |
| `color` | `"#cccccc"` | any matplotlib colour; `"original"` keeps a mesh's own materials. Ignored for (N, 4) and (N, 6) point clouds |
| `location` | `[0, 0, 0]` | file units |
| `rotation` | `[0, 0, 0]` | degrees about x, y, z, pivoting on the file's origin |
| `scale` | `1.0` | uniform |
| `radius` | automatic | point clouds, file units |
| `radius_scale` | `1.0` | point clouds, multiplier on the automatic radius |
| `smooth` | `true` | meshes, smooth shading |

The world is Z-up. `--color`, `--radius` and `--radius-scale` set defaults that
entries override. The same structure in JSON (`{"objects": [{...}, ...]}`) also
works.
