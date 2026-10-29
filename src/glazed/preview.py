"""`glazed --preview`: the scene in the browser, framed and lit like the render.

Orbit and adjust the lighting there, then copy the matching glazed command, or
render it with Cycles at preview quality when bpy is installed. The server needs
only numpy (matplotlib, when present, gives exact colormaps), so it runs from a
research environment too.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import mimetypes
import shlex
import subprocess
import sys
import tempfile
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import numpy as np

from .cli import to_argv
from .io import POINT_CLOUD_SUFFIXES, AssetSpec, point_radius

PAGE = Path(__file__).with_name("preview.html")
# The options the page controls; everything else keeps its command-line value.
CONTROLS = ("azim", "elev", "distance", "lens", "key", "ambient", "key_azim", "key_elev",
            "exposure", "bg", "transparent", "cmap", "vmin", "vmax", "res")
ANIMATION = ("frames", "fps", "turns", "elev_amp", "dolly")
QUICK_RENDER = {"samples": 32, "supersample": 1, "mode": ["still"], "colorbar": False,
                "save_blend": False}
QUICK_WIDTH = 640


class Preview:
    def __init__(self, specs: list[AssetSpec], args: argparse.Namespace):
        self.specs, self.args = specs, args
        self.clouds = {i: np.load(spec.path).astype(np.float32) for i, spec in enumerate(specs)
                       if Path(spec.path).suffix.lower() in POINT_CLOUD_SUFFIXES}
        self.scene = {
            "objects": [self.describe(i, spec) for i, spec in enumerate(specs)],
            "options": {key: getattr(args, key) for key in CONTROLS},
            "animation": {key: getattr(args, key) for key in ANIMATION},
            "bgHex": css_color(args.bg),
            "canRender": importlib.util.find_spec("bpy") is not None,
        }

    def describe(self, i: int, spec: AssetSpec) -> dict:
        file = Path(spec.path)
        entry = {"name": file.name, "suffix": file.suffix.lower(),
                 "color": spec.color if spec.color == "original" else css_color(spec.color),
                 "location": list(spec.location), "rotation": list(spec.rotation),
                 "scale": spec.scale, "smooth": spec.smooth}
        if i in self.clouds:
            data = self.clouds[i]
            if data.ndim != 2 or data.shape[1] not in (3, 4, 6):
                raise ValueError(f"{file}: expected an (N, 3|4|6) array, got {data.shape}")
            entry.update(url=f"points/{i}", columns=data.shape[1],
                         radius=point_radius(data[:, :3], spec.radius, spec.radius_scale))
        else:
            entry["url"] = f"files/{i}/{quote(file.name)}"
        return entry

    def file(self, i: int, name: str) -> Path | None:
        """A file beside scene entry `i`: the asset itself, or a glTF's buffers and textures."""
        folder = Path(self.specs[i].path).resolve().parent
        path = (folder / name).resolve()
        return path if path.is_relative_to(folder) and path.is_file() else None

    def values(self, options: dict) -> dict:
        controlled = {key: value for key, value in options.items() if key in CONTROLS}
        return {**vars(self.args), **controlled, "preview": False, "port": None}

    def command(self, options: dict) -> str:
        return shlex.join(["glazed", *to_argv(self.values(options))])

    def render(self, options: dict) -> bytes:
        """A Cycles still at preview quality, in a fresh process so bpy starts clean."""
        values = self.values(options)
        width, height = values["res"]
        with tempfile.TemporaryDirectory() as tmp:
            values.update(QUICK_RENDER, res=[QUICK_WIDTH, round(QUICK_WIDTH * height / width)],
                          cmap=values["cmap"][:1], out=str(Path(tmp, "preview")))
            subprocess.run([sys.executable, "-m", "glazed", *to_argv(values)],
                           check=True, capture_output=True, text=True)
            return Path(tmp, "preview.png").read_bytes()


def css_color(spec: str) -> str:
    """A matplotlib colour spec as hex. Without matplotlib, CSS names and hex pass through."""
    try:
        from matplotlib.colors import to_hex
    except ImportError:
        return spec
    return to_hex(spec)


def colormap_table(name: str) -> list | None:
    """256 sRGB entries of a matplotlib colormap, or None without matplotlib or that name."""
    try:
        from matplotlib import colormaps
        return colormaps[name](np.linspace(0.0, 1.0, 256))[:, :3].round(4).tolist()
    except (ImportError, KeyError):
        return None


def make_handler(preview: Preview) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route, _, rest = unquote(urlparse(self.path).path).strip("/").partition("/")
            try:
                if route == "":
                    self.send(PAGE.read_bytes(), "text/html; charset=utf-8")
                elif route == "scene.json":
                    self.send(json.dumps(preview.scene).encode(), "application/json")
                elif route == "points":
                    self.send(preview.clouds[int(rest)].tobytes(), "application/octet-stream")
                elif route == "files" and (file := preview.file(*parse_file(rest))):
                    kind = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                    self.send(file.read_bytes(), kind)
                elif route == "colormap" and (table := colormap_table(rest)):
                    self.send(json.dumps(table).encode(), "application/json")
                else:
                    self.send_error(404)
            except (KeyError, IndexError, ValueError):
                self.send_error(404)

        def do_POST(self):
            options = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            route = self.path.strip("/")
            if route == "command":
                self.send(json.dumps({"command": preview.command(options)}).encode(),
                          "application/json")
            elif route == "render":
                try:
                    self.send(preview.render(options), "image/png")
                except subprocess.CalledProcessError as err:
                    message = (err.stderr or err.stdout or "render failed").strip()[-3000:]
                    self.send(message.encode(), "text/plain; charset=utf-8", status=500)
            else:
                self.send_error(404)

        def send(self, body: bytes, kind: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


def parse_file(rest: str) -> tuple[int, str]:
    index, _, name = rest.partition("/")
    return int(index), name


def serve(specs: list[AssetSpec], args: argparse.Namespace) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", args.port or 0), make_handler(Preview(specs, args)))
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"[i] preview at {url} (Ctrl+C to stop)", flush=True)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
