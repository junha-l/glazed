"""The `glazed` command: render asset and scene files from the shell."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .io import MESH_SUFFIXES, POINT_CLOUD_SUFFIXES, SCENE_SUFFIXES, AssetSpec, read_inputs
from .settings import MODES, Animation, Colormap, Lighting, RenderSettings, View


class HelpFormatter(argparse.ArgumentDefaultsHelpFormatter):
    """Shows defaults, except None ones, whose help already says what happens instead."""

    def _get_help_string(self, action):
        return action.help if action.default is None else super()._get_help_string(action)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Studio-lit Cycles renders of point clouds, meshes, and scenes mixing both.",
        formatter_class=HelpFormatter)
    p.add_argument("inputs", nargs="+", metavar="INPUT",
                   help=f"asset files ({' '.join(POINT_CLOUD_SUFFIXES + MESH_SUFFIXES)}) "
                        f"or scene files ({' '.join(SCENE_SUFFIXES)})")
    p.add_argument("--out", help="output path; the mode adds .png, .mp4 or .gif "
                                 "(default: outs/<first input's name>)")
    p.add_argument("--mode", nargs="+", default=["still"], choices=MODES)

    g = p.add_argument_group("objects (scene file entries override these)")
    g.add_argument("--color", default=AssetSpec.color,
                   help="colour of anything without per-point values")
    g.add_argument("--radius", type=float, help="point radius in data units (default: automatic)")
    g.add_argument("--radius-scale", type=float, default=AssetSpec.radius_scale,
                   help="multiplier on the automatic point radius")

    g = p.add_argument_group("colormap")
    g.add_argument("--cmap", nargs="+", default=list(Colormap.names),
                   help="one render pass per colormap")
    g.add_argument("--vmin", type=float, help="colormap's low end (default: data min)")
    g.add_argument("--vmax", type=float, help="colormap's high end (default: data max)")
    g.add_argument("--colorbar", action="store_true", help="also write colorbar.png")
    g.add_argument("--colorbar-label", default=Colormap.label)

    g = p.add_argument_group("camera")
    g.add_argument("--azim", type=float, default=View.azim, help="degrees")
    g.add_argument("--elev", type=float, default=View.elev, help="degrees")
    g.add_argument("--distance", type=float,
                   help="multiple of the scene's half-size (default: fit the scene in frame)")
    g.add_argument("--lens", type=float, default=View.lens,
                   help="mm; shorter = stronger perspective")
    g.add_argument("--waypoints",
                   help='camera path JSON {"eye": [[x, y, z], ...], "target": [...], "loop": true}')

    g = p.add_argument_group("animation")
    g.add_argument("--frames", type=int, default=Animation.frames)
    g.add_argument("--fps", type=int, default=Animation.fps)
    g.add_argument("--turns", type=float, default=Animation.turns)
    g.add_argument("--elev-amp", type=float, default=Animation.elev_amp,
                   help="degrees of up-down sway")
    g.add_argument("--dolly", type=float, default=Animation.dolly,
                   help="fractional push-in over the shot, e.g. 0.15")
    g.add_argument("--ease", action="store_true", help="slow in/out; breaks a seamless loop")
    g.add_argument("--gif-width", type=int, default=Animation.gif_width)
    g.add_argument("--keep-frames", action=argparse.BooleanOptionalAction,
                   default=Animation.keep_frames)

    g = p.add_argument_group("lighting")
    g.add_argument("--key", type=float, default=Lighting.key, help="key light multiplier")
    g.add_argument("--ambient", type=float, default=Lighting.ambient,
                   help="environment multiplier; lower = darker shadows, more contrast")
    g.add_argument("--key-azim", type=float, default=Lighting.key_azim,
                   help="key angle from the camera, degrees; nearer 0 = flatter, +-90 = more depth")
    g.add_argument("--key-elev", type=float, default=Lighting.key_elev,
                   help="key height, degrees; lower = stronger shading")
    g.add_argument("--exposure", type=float, default=RenderSettings.exposure,
                   help="stops; -1 halves the brightness")
    g.add_argument("--bg", default=RenderSettings.background, help="backdrop colour")
    g.add_argument("--transparent", action="store_true", help="keep the background transparent")

    g = p.add_argument_group("quality")
    g.add_argument("--res", type=int, nargs=2, default=list(RenderSettings.resolution),
                   metavar=("W", "H"))
    g.add_argument("--supersample", type=int, default=RenderSettings.supersample,
                   help="render at Nx, then box-filter down to --res; 1 to disable")
    g.add_argument("--samples", type=int, default=RenderSettings.samples)
    g.add_argument("--gpu", action="store_true")
    g.add_argument("--save-blend", action="store_true",
                   help="also save a .blend for tweaking in Blender")

    g = p.add_argument_group("preview")
    g.add_argument("--preview", action="store_true",
                   help="instead of rendering, open the scene in the browser to pick the view "
                        "and lighting, and get the matching command")
    g.add_argument("--port", type=int, help="preview server port (default: any free one)")
    return p


def parse_args(argv=None) -> argparse.Namespace:
    if argv is None:  # under `blender -b -P render.py -- <args>`, ours follow the "--"
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    return build_parser().parse_args(argv)


def to_argv(values: dict) -> list[str]:
    """Arguments that parse back to `values`, leaving out options at their defaults."""
    argv = [str(path) for path in values["inputs"]]
    for action in build_parser()._actions:
        value = values.get(action.dest, action.default)
        if not action.option_strings or value == action.default:
            continue
        if isinstance(action, argparse.BooleanOptionalAction):
            argv.append(action.option_strings[0 if value else 1])
        elif action.nargs == 0:
            argv.append(action.option_strings[0])
        else:
            items = value if isinstance(value, (list, tuple)) else [value]
            argv += [action.option_strings[0], *map(str, items)]
    return argv


def main(argv=None) -> None:
    args = parse_args(argv)
    defaults = {"color": args.color, "radius": args.radius, "radius_scale": args.radius_scale}
    try:
        specs = read_inputs(args.inputs, defaults)
    except (OSError, ValueError, TypeError) as err:
        sys.exit(f"glazed: {err}")
    if args.preview:
        from .preview import serve
        serve(specs, args)
        return
    try:
        from .render import render
    except ImportError as err:
        sys.exit(f"glazed: rendering needs Blender's bpy ({err}).\n"
                 "Install it in a Python 3.13 environment: pip install 'glazed[render]'")

    render(
        specs, args.out or str(Path("outs") / Path(args.inputs[0]).stem), args.mode,
        settings=RenderSettings(resolution=tuple(args.res), supersample=args.supersample,
                                samples=args.samples, exposure=args.exposure, gpu=args.gpu,
                                background=None if args.transparent else args.bg),
        lighting=Lighting(key=args.key, ambient=args.ambient, key_azim=args.key_azim,
                          key_elev=args.key_elev),
        view=View(azim=args.azim, elev=args.elev, distance=args.distance, lens=args.lens,
                  waypoints=args.waypoints),
        animation=Animation(frames=args.frames, fps=args.fps, turns=args.turns,
                            elev_amp=args.elev_amp, dolly=args.dolly, ease=args.ease,
                            gif_width=args.gif_width, keep_frames=args.keep_frames),
        colormap=Colormap(names=tuple(args.cmap), vmin=args.vmin, vmax=args.vmax,
                          colorbar=args.colorbar, label=args.colorbar_label),
        save_blend=args.save_blend,
    )
