---
name: glazed-render
description: Turn a research project's 3D outputs (point clouds, meshes, predicted poses, generated or reconstructed shapes, hand-object grasps) into glazed scene files and render publication-quality stills and turntable videos with the glazed Blender renderer. Covers exporting tensors with glazed.io (PLY meshes, .npy point clouds, a scene .toml), keeping the parts of a scene aligned, and running the render. Use this whenever the user wants to render, visualize, or make figures, panels, or videos of 3D model outputs or inputs, compare predictions with ground truth in 3D, or mentions glazed, glazed.io, or scene.toml, even if they only say "make nice pictures of these results".
---

# Rendering project outputs with glazed

glazed renders 3D files plus a small scene file into studio-lit Blender Cycles
images. It comes in two parts, which live in different Python environments:

- **`glazed.io`** writes the files. It needs only numpy, runs on Python >= 3.9, and
  belongs in this project's own environment: `pip install glazed` (or
  `pip install <path or git URL of glazed>` while it's unpublished).
- **The renderer** needs Blender's `bpy`, which pins Python 3.13, so it lives in a
  separate environment (`pip install "glazed[render]"`). Run it through that
  environment's `glazed` executable. Don't install the render extra into the
  project's environment. The `glazed` command of a plain install only prints how
  to get rendering. If you don't know where the render environment is, ask the
  user, and suggest recording the path in the project's CLAUDE.md for next time.

Before exporting, read the domain guide that matches the project, if there is one:

- `references/hand-object-grasps.md`: dexterous or robotic grasps, i.e. a posed hand
  (from predicted grasp parameters) and an object.

## 1. Find the geometry

Work out what to show, and how the codebase already produces it. Reuse the
project's own code for geometry. Re-deriving it risks output that looks plausible
but is subtly wrong.

- **Outputs.** The model may predict points or meshes directly, or parameters that
  need decoding: poses through forward kinematics, latents through a decoder,
  occupancy or SDF grids through marching cubes. Search for existing visualization
  or evaluation code (`visualize`, `plot`, `render`, `open3d`, `trimesh`, `plotly`,
  `export`, `.ply`, `.obj`). Those helpers usually already turn outputs into
  vertices, faces, or points.
- **Inputs.** Export conditioning inputs (objects, partial scans, scenes) exactly as
  the model saw them. Datasets often normalize or rescale samples, and a prediction
  only lines up with its input in the same coordinates. Either export everything in
  the model's normalized space, or undo the normalization for every part alike.
- **Mesh or points**, chosen per part as the user asks:
  - Mesh: vertices and faces.
  - Points: sample the surface densely with `sample_surface`, about 20k-50k points
    for a main object. Sparse sets (a few hundred points) render as a handful of
    big spheres.
  - Geometry that only exists as points can only be rendered as points. Tell the
    user if they asked for a mesh.
- **Values.** A per-point quantity (error, contact, uncertainty, a predicted field)
  can color a point cloud through a colormap.
- **Batches.** Index the batch dimension and export one sample per scene.

## 2. Export with glazed.io

```python
from pathlib import Path
from glazed.io import check_alignment, check_scene, sample_surface, save_mesh, save_points, write_scene

out = Path("renders/run_name/sample_000")
out.mkdir(parents=True, exist_ok=True)

save_mesh(out / "input.ply", in_vertices, in_faces)
save_points(out / "prediction.npy", pred_points, values=per_point_error)  # values optional
check_alignment(pred_points, sample_surface(in_vertices, in_faces, 20000),
                names=("prediction", "input"))  # read what it prints (section 3)

write_scene(out / "scene.toml", [
    {"path": out / "input.ply", "color": "#c9ccd1"},
    {"path": out / "prediction.npy"},
])
assert not check_scene(out / "scene.toml")
```

Every function takes numpy arrays or torch tensors on any device.

| Function | Use |
|---|---|
| `save_points(path, xyz, values=None, rgb=None)` | `.npy` cloud: (N, 3); with `values`, (N, 4) colormapped; with `rgb` in [0, 1], (N, 6) |
| `save_mesh(path, vertices, faces)` | Binary PLY, triangles or quads |
| `sample_surface(vertices, faces, n)` | Uniform points on a mesh surface |
| `to_z_up(xyz, up="y")` | Rotate so the given axis becomes +z |
| `check_alignment(a, b, names)` | Sizes and closest distance of two parts |
| `grid_locations(count, spacing)` | Offsets for laying out several results |
| `write_scene(path, objects)` | The scene .toml, from dicts or `AssetSpec`s |
| `check_scene(path)` | Missing files, bad arrays, format pitfalls, without rendering |

## 3. Keep the parts aligned

glazed centers and rescales the whole scene for rendering, but never moves one file
relative to another. Alignment is the exporter's job.

- **One frame, one unit.** Every part must share coordinates and units.
  `check_alignment` prints the sizes and the closest distance between two parts:
  - Sizes about 1000x apart mean millimeters vs meters.
  - A gap far larger than the task implies means the parts are in different frames,
    for example a prediction in world coordinates and its input in canonical ones.

  Pass surface samples, not raw mesh vertices: on large flat faces the vertices sit
  far from the surface the other part touches, which inflates the gap.
- **Write meshes with `save_mesh` (PLY).** Blender reads OBJ files as Y-up and
  rotates them to Z-up, while PLY, STL and `.npy` are read as stored. An OBJ written
  in the same frame as the other files comes out tilted 90 degrees.
- **Z is up.** glazed puts the floor under the scene's lowest point along z and
  lights from above. If the project's frame is Y-up (common for ShapeNet- or
  Objaverse-derived data), apply `to_z_up(..., up="y")` to every array of the scene.
- **One quantity per scene.** All files with per-point values share one colormap
  range. Give values to one quantity, and solid colors to everything else. Neutral
  context (inputs, ground truth) reads well in gray `#c9ccd1`; accents: `#4c78a8`
  (blue), `#e45756` (red), `#e0a96d` (warm).
- **Check before rendering.** `check_scene` catches missing files, malformed arrays,
  and OBJ pitfalls in a second, while a render takes minutes.

## 4. Several results

- **One scene per result** gives individually framed panels to assemble in LaTeX or
  matplotlib. Each scene is sized to its own bounding box, so panels can differ
  slightly in scale.
- **One scene for many results** keeps the scale identical. Lay them out with
  `grid_locations(count, spacing)`, giving every file of one result the same
  `location`, with a spacing of about 1.5x the largest part. Render a row from the
  front with `--azim -90`.

## 5. Scene file reference

`write_scene` produces this format: one `[[objects]]` table per file.

```toml
[[objects]]
path = "input.ply"        # relative to the scene file
color = "#c9ccd1"

[[objects]]
path = "prediction.npy"
location = [0.3, 0, 0]    # file units
```

| Key | Default | Meaning |
|---|---|---|
| `path` | required | `.npy` point cloud, or a `.ply .stl .obj .glb .gltf .fbx` mesh |
| `color` | `"#cccccc"` | Any matplotlib color. Ignored for (N, 4) and (N, 6) clouds. `"original"` keeps a mesh's own materials |
| `location` | `[0, 0, 0]` | Offset, in file units |
| `rotation` | `[0, 0, 0]` | Degrees about x, y, z, pivoting on the file's origin |
| `scale` | `1.0` | Uniform |
| `radius` | automatic | Point sphere radius, in file units |
| `radius_scale` | `1.0` | Multiplier on the automatic radius; raise it to close gaps |
| `smooth` | `true` | Smooth shading for meshes |

## 6. Render

```bash
<render env>/bin/glazed renders/run_name/sample_000/scene.toml --gpu --out renders/run_name/sample_000/render
```

`--out` is a path without an extension; the mode adds it. This writes
`render.png` next to the scene, or `render.mp4` / `render.gif` with frames in
`render_frames/` for videos, and `render_<colormap>.png` per colormap when several
are given. Pass `--out` explicitly: by default it is `outs/<scene file name>`
relative to the working directory, so every `scene.toml` would land on the same
`outs/scene.png`.

- **Preview first.** Try a few views at low quality
  (`--res 480 360 --samples 32 --supersample 1`, varying `--azim` and `--elev`),
  look at them, then render the chosen view at full quality. Pick a view where the
  interesting part isn't hidden behind something else. If the user would rather
  choose the view themselves, suggest they run `glazed <scene> --preview`: it opens
  an interactive browser preview and gives back the matching command.
- **Colormaps.** `--cmap`, `--vmin`, `--vmax`, `--colorbar`. For quantities that
  are zero almost everywhere (errors, contact), use a colormap that starts light,
  such as `--cmap Reds --vmin 0`. With viridis, the large zero region turns dark
  purple and hides the shape.
- **Look.** `--key-elev 25 --ambient 0.6` gives stronger shading on curved
  surfaces. `--transparent` is for compositing onto a page; `--bg "#2b2f36"` for
  dark slides.
- **Video.** `--mode mp4 --res 1280 720 --supersample 1 --samples 128` renders a
  turntable.
- `glazed --help` lists every option.

Look at the rendered PNG before reporting back. If parts float apart, are rotated
90 degrees, or differ wildly in size, revisit section 3.
