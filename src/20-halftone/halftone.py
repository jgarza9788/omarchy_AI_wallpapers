"""20 — Halftone: the Blender renders (01 Monolith, 08 Shroud) re-screened as dot-matrix prints.

Riffs on the dot-matrix and halftone backgrounds that ship with Omarchy's
vantablack, matte-black and solitude themes. An existing 4K render is reduced to
luminance and screened on a 45° grid. Each dot's area is proportional to the
brightness at its cell centre, and the dot is drawn analytically with an
anti-aliased edge. Dots are inked from the theme accent (small) to the foreground
(large) on the theme background: two inks, like a riso print.

Usage: python3 src/20-halftone/halftone.py [--scheme solitude|all] [--scale 0.25]
"""
import math
import pathlib
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import FONTS, H, OUTPUT, W, box_blur, hex2arr, out_path, save_rgb, scheme_args  # noqa: E402

SOURCES = {   # scheme -> source render
    "solitude": "08-shroud/shroud--rose-pine.png",
    "vantablack": "08-shroud/shroud--retro-82.png",
    "matte-black": "01-monolith/monolith--gruvbox.png",
    "hackerman": "01-monolith/monolith--osaka-jade.png",
}
SCHEMES = list(SOURCES)
CELL = 22.0            # screen pitch at 4K
ANGLE = math.radians(45)


def luminance(path, w, h):
    raw = subprocess.run(["magick", str(path), "-resize", f"{w}x{h}!", "-colorspace", "gray", "-depth", "8", "gray:-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w).astype(np.float32) / 255


def render(name, pal, s):
    w, h = int(W * s), int(H * s)
    src = OUTPUT / SOURCES[name]
    lum = luminance(src, w, h)
    lum = box_blur(lum, CELL * s * 0.35, passes=2)          # average over roughly one cell
    lo, hi = np.percentile(lum, [12, 99.5])          # clip the darkest 12% to bare paper: negative space
    lum = np.clip((lum - lo) / (hi - lo), 0, 1) ** 1.1

    cell = CELL * s
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ca, sa = math.cos(ANGLE), math.sin(ANGLE)
    u = (xx * ca + yy * sa) / cell
    v = (-xx * sa + yy * ca) / cell
    iu, iv = np.floor(u), np.floor(v)
    du, dv = (u - iu - 0.5) * cell, (v - iv - 0.5) * cell
    # brightness sampled at each cell's centre (rotate the centre back to image space)
    cu, cv = (iu + 0.5) * cell, (iv + 0.5) * cell
    cx = np.clip(cu * ca - cv * sa, 0, w - 1).astype(int)
    cy = np.clip(cu * sa + cv * ca, 0, h - 1).astype(int)
    b = lum[cy, cx]
    radius = cell * 0.5 * np.sqrt(b) * 1.18                  # area ∝ brightness (slight overlap at full)
    cover = np.clip(radius - np.hypot(du, dv) + 0.5, 0, 1)[..., None]

    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    paper = c["background"]
    ink = c["accent"][None, None] * (1 - b[..., None]) + c.get("bright_foreground", c["foreground"]) * b[..., None]
    img = paper * (1 - cover) + ink * cover

    font = str(FONTS / "SpaceMono" / "SpaceMonoNerdFontMono-Regular.ttf")
    dim = pal.get("dark_foreground", pal["foreground"])
    m = int(110 * s)
    label = SOURCES[name].split("/")[1].replace(".png", "").replace("--", " / ")
    post = ["-font", font, "-pointsize", str(max(int(24 * s), 7)), "-fill", dim, "-kerning", str(max(int(6 * s), 1)),
            "-gravity", "southwest", "-annotate", f"+{m}+{m}",
            f"OMARCHY  ·  HALFTONE  ·  {label.upper()}  ·  {CELL:.0f}PX 45°  ·  {name.upper()}"]
    save_rgb(img, out_path("20-halftone", f"halftone--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
