"""Shared helpers for the numpy-based generators (no PIL: ImageMagick does I/O)."""
import pathlib
import subprocess
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "palettes"))
import palettes  # noqa: E402

W, H = 3840, 2160
BRAND = ROOT / "assets" / "brand"
FONTS = ROOT / "assets" / "fonts"
OUTPUT = ROOT / "output"


def hex2arr(h):
    return np.array(palettes.rgb(h), dtype=np.float32)


def load_gray(path, w, h, extra=()):
    """Load an image as float32 luminance-ish alpha mask in [0,1], fitted into w x h."""
    raw = subprocess.run(
        ["magick", str(path), "-background", "black", "-alpha", "remove", *extra,
         "-resize", f"{w}x{h}", "-gravity", "center", "-extent", f"{w}x{h}",
         "-colorspace", "gray", "-depth", "8", "gray:-"],
        check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w).astype(np.float32) / 255


def load_alpha(path, w, h, extra=()):
    """Load an image's alpha channel (the logo PNGs are coloured on transparent)."""
    raw = subprocess.run(
        ["magick", str(path), "-alpha", "extract", *extra,
         "-resize", f"{w}x{h}", "-gravity", "center", "-background", "black",
         "-extent", f"{w}x{h}", "-depth", "8", "gray:-"],
        check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w).astype(np.float32) / 255


def save_rgb(img, path, post=()):
    """Write float RGB [0,1] array to PNG, optionally piping through extra magick ops."""
    h, w, _ = img.shape
    # triangular dither (±1 LSB) so smooth dark gradients don't band at 8 bits
    rng = np.random.default_rng(0)
    tpdf = (rng.random((h, w, 1), dtype=np.float32) - rng.random((h, w, 1), dtype=np.float32))
    data = (np.clip(np.clip(img, 0, 1) * 255 + 0.5 + tpdf, 0, 255)).astype(np.uint8).tobytes()
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["magick", "-size", f"{w}x{h}", "-depth", "8", "rgb:-", *post, str(path)],
                   input=data, check=True)
    print(f"wrote {path}")


def value_noise(h, w, cell, rng, octaves=5, persistence=0.5):
    """Smooth fBm value noise in [0,1] using cosine-interpolated random lattices."""
    total = np.zeros((h, w), np.float32)
    amp, norm = 1.0, 0.0
    for _ in range(octaves):
        gh, gw = h // cell + 2, w // cell + 2
        grid = rng.random((gh, gw)).astype(np.float32)
        ys = np.arange(h, dtype=np.float32) / cell
        xs = np.arange(w, dtype=np.float32) / cell
        y0, x0 = ys.astype(int), xs.astype(int)
        ty = (1 - np.cos((ys - y0) * np.pi)) / 2
        tx = (1 - np.cos((xs - x0) * np.pi)) / 2
        a = grid[y0][:, x0]
        b = grid[y0][:, x0 + 1]
        c = grid[y0 + 1][:, x0]
        d = grid[y0 + 1][:, x0 + 1]
        top = a + (b - a) * tx[None, :]
        bot = c + (d - c) * tx[None, :]
        total += amp * (top + (bot - top) * ty[:, None])
        norm += amp
        amp *= persistence
        cell = max(cell // 2, 2)
    return total / norm


def box_blur(a, r, passes=3):
    """Approximate gaussian blur with repeated separable box filters."""
    r = max(int(r), 1)
    for _ in range(passes):
        for axis in (0, 1):
            pad = np.pad(a, [(r + 1, r) if ax == axis else (0, 0) for ax in (0, 1)], mode="edge")
            c = np.cumsum(pad, axis=axis, dtype=np.float64)
            if axis == 0:
                a = ((c[2 * r + 1:] - c[:-2 * r - 1]) / (2 * r + 1)).astype(np.float32)
            else:
                a = ((c[:, 2 * r + 1:] - c[:, :-2 * r - 1]) / (2 * r + 1)).astype(np.float32)
    return a


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def ramp(stops, t):
    """Interpolate a list of RGB arrays along t in [0,1] (t is an array)."""
    stops = np.stack(stops)
    n = len(stops) - 1
    x = np.clip(t, 0, 1) * n
    i = np.minimum(x.astype(int), n - 1)
    f = (x - i)[..., None]
    return stops[i] * (1 - f) + stops[i + 1] * f


def scheme_args(default_schemes, argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheme", default="all")
    ap.add_argument("--scale", type=float, default=1.0, help="preview scale, e.g. 0.25")
    args = ap.parse_args(argv)
    names = default_schemes if args.scheme == "all" else [args.scheme]
    return names, args.scale, palettes.load()


def out_path(folder, stem, scale):
    """Full-size renders go to output/<folder>/; scaled previews to .wip/ (scratch)."""
    if scale == 1:
        return OUTPUT / folder / f"{stem}.png"
    return ROOT / ".wip" / f"{stem}@{scale}.png"
