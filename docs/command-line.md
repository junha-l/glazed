# Command line

[← README](../README.md)

The [preview](../README.md#the-preview) hands back a `glazed` command for its
shot; this page covers every option such a command can carry. `glazed --help`
lists them too.

```bash
glazed examples/glazed_donut.toml --elev 35 --gpu        # dough and glaze meshes, RGB sprinkles
glazed examples/donut.npy --gpu                          # a point cloud, coloured by height
glazed examples/glazed_donut.toml --mode mp4 gif --gpu   # a turntable video and GIF
glazed mesh.ply cloud.npy --bg "#2b2f36" --gpu           # any files, dark backdrop
```

## Outputs

Output goes to `outs/<first input's name>` plus an extension per mode. Set the
path with `--out figs/teaser`; `--out figs/teaser.png` works too, without doubling
the extension.

| Output | Path |
|---|---|
| Still (`--mode still`, the default) | `outs/glazed_donut.png` |
| Video and GIF (`--mode mp4 gif`) | `outs/glazed_donut.mp4`, `.gif`, with frames kept in `outs/glazed_donut_frames/` |
| Frames only (`--mode png`) | `outs/glazed_donut_frames/frame_00000.png`, ... |
| Several colormaps (`--cmap viridis magma`) | `outs/donut_viridis.png`, `outs/donut_magma.png` |
| `--colorbar`, `--save-blend` | `outs/donut_colorbar.png`, `outs/donut.blend`, suffixed per colormap like the renders |

`--no-keep-frames` deletes the frames once the video is encoded.

## The shot

The studio is one soft key light from the side, white ambient fill, and a floor
that only catches shadows. The lights turn with the camera, like a turntable under
fixed lights, so an orbit looks the same from every angle. The preview's panel
sets all of these; every other option comes from the command that starts it.

| Option | Default | | In the preview |
|---|---|---|---|
| `--azim`, `--elev` | `45`, `22` | camera angle, degrees; an orbit starts here | View, or orbit |
| `--distance` | fits the scene | multiple of the scene's half-size | View; **Auto** fits |
| `--lens` | `50` | mm; shorter gives stronger perspective | View |
| `--exposure` | `0` | stops; `-1` halves the brightness | Light |
| `--ambient` | `1` | fill light; lower gives darker shadows and more contrast | Light |
| `--key` | `1` | key light strength | Light › Key light |
| `--key-azim` | `-90` | key angle from the camera, degrees, negative to its left; near 0 looks flat, near ±90 shows the most depth | Light › Key light |
| `--key-elev` | `35` | key height, degrees; lower gives stronger shading on curved surfaces | Light › Key light |
| `--bg` | `white` | backdrop, any matplotlib colour | Backdrop |
| `--transparent` | off | leaves the backdrop transparent, for compositing | Backdrop |
| `--cmap`, `--vmin`, `--vmax` | `viridis`, data range | colours per-point values; the range is shared across the scene | Colour |
| `--res` | `1400 1050` | image size | Output |
| `--fps` | `30` | video speed | fps, under the image |

## Turntables and camera paths

Video modes orbit the scene, by default `--frames 120 --fps 30 --turns 1`, which
loops seamlessly. `--elev-amp 10` adds an up-and-down sway, `--dolly 0.15` pushes
in by 15% over the shot, and `--ease` slows the start and end, which breaks the
loop. `--gif-width` sets the GIF's width (720). The preview's **Turntable** plays
the orbit, without `--ease`.

`--waypoints path.json` replaces the orbit with a smooth spline through camera
positions, which the preview doesn't play. Coordinates are in normalised scene
units: the scene is centred on the origin with a largest half-side of 1. `target`
is optional and defaults to the orbit's centre.

```json
{"eye": [[3, -3, 1], [3, 3, 1.5], [-3, 3, 1]], "target": [[0, 0, 0]], "loop": true}
```

## Animated files

A USD file with animation, such as a simulation replay, plays in video modes: one
video frame per frame of the file, so the file sets the length instead of
`--frames`. `--every 2` renders every 2nd frame. A 60 fps file then plays in real
time at the default `--fps 30`. The floor and framing cover the whole animation.
A still renders the first frame.

```bash
glazed examples/grasp.usd --mode mp4 --every 2 --turns 0 --best-view --color original \
    --res 1280 720 --samples 128 --supersample 1 --gpu
```

`--turns 0` keeps the camera still. `--color original` keeps the file's own
materials. `--best-view` picks the view, as below.

## Best view

`--best-view` replaces `--azim` with the azimuth, in 15 degree steps, that hides
the least of the scene, such as fingers behind the object they hold. Each part (each
mesh in a file, each point cloud) counts equally: the score is the share of points
on it that the camera can see, averaged over the parts and, for an animation, over
a few frames. Ties go to the angle nearest `--azim`, and `--elev` is kept. Without
`--distance`, it also frames the scene as closely as the camera's path allows,
instead of leaving room for a whole orbit. The pick happens at render time, so the
preview doesn't show it: started with `--best-view`, its command keeps the option,
and the render replaces the preview's azimuth.

## Quality

Renders default to `--res 1400 1050 --samples 256 --supersample 2`, rendering at
twice the resolution and filtering down for clean edges. `--gpu` renders and
denoises on the first of OptiX, CUDA, HIP, Metal, or oneAPI it finds, and falls back
to the CPU. For a quick draft, use the preview's Render, or
`--res 480 360 --samples 32 --supersample 1`; for videos,
`--res 1280 720 --samples 128 --supersample 1` keeps frame times down.
`--save-blend` also saves the scene as a `.blend` to adjust by hand in Blender.

## Python API

In the render environment:

```python
from glazed.io import AssetSpec
from glazed.render import render
from glazed.settings import RenderSettings, View

render([AssetSpec("examples/donut.ply", color="#d9a066"),
        AssetSpec("examples/glaze.ply", color="#f4a6c6"),
        AssetSpec("examples/sprinkles.npy", radius=0.0009)],
       out="outs/glazed_donut", settings=RenderSettings(gpu=True), view=View(elev=35))
```

`out` works like `--out` and defaults to `outs/render`. `modes` takes the
`--mode` values, e.g. `modes=("mp4", "gif")`, and the other options live in
`glazed.settings` as dataclasses: `RenderSettings`, `Lighting`, `View`,
`Animation`, and `Colormap`.
