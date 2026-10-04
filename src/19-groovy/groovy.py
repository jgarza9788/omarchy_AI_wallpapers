"""19 — Groovy: 70s stripes streaming out of the Omarchy mark.

Riffs on the retro stripe-ribbon backgrounds that ship with Omarchy's ristretto
theme. A Euclidean distance field (ImageMagick's morphology Distance) is taken
from the Omarchy square mark merged with a ray running off the right edge, then
quantised into concentric bands, so the stripes hug the mark and then stream
off-screen like a racing stripe. A slow sinusoidal warp gives them swoop.
Bands are painted outer to inner with anti-aliased outer edges, and film grain is added.

Usage: python3 src/19-groovy/groovy.py [--scheme ristretto|all] [--scale 0.25]
"""
import pathlib
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import BRAND, FONTS, H, W, hex2arr, load_alpha, out_path, save_rgb, scheme_args  # noqa: E402

SCHEMES = ["ristretto", "gruvbox", "retro-82", "catppuccin-latte"]
DS = 4            # the distance field is computed at 1/4 resolution, then upsampled
BANDS = 6


def distance_field(mask, w, h):
    """Distance (in full-res px) from every pixel to the nearest mask pixel."""
    sh, sw = mask.shape
    raw = (np.where(mask > 0.5, 0, 255)).astype(np.uint8).tobytes()
    out = subprocess.run(
        ["magick", "-size", f"{sw}x{sh}", "-depth", "8", "gray:-",
         "-morphology", "Distance", "Euclidean:4,10", "-resize", f"{w}x{h}!", "-depth", "16", "gray:-"],
        input=raw, check=True, capture_output=True).stdout
    d = np.frombuffer(out, np.uint16).reshape(h, w).astype(np.float32)
    return d / 10.0 * (w / sw)          # undo the kernel scale, then the downsample


def render(name, pal, s):
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    bg = c["background"]
    seq = [c["yellow"], c.get("orange", c["red"]), c["red"], c["magenta"], c.get("brown", c["blue"]), c["accent"]]

    # mask at low res: the Omarchy mark plus a ray to the right edge
    sw, sh = W // DS, H // DS
    size = int(sh * 0.34)
    cx, cy = int(sw * 0.3), int(sh * 0.5)
    mark = load_alpha(BRAND / "omarchy-logo.png", size, size)
    mask = np.zeros((sh, sw), np.float32)
    mask[cy - size // 2:cy - size // 2 + size, cx - size // 2:cx - size // 2 + size] = mark
    solid = mask.copy()
    mask[cy - 1:cy + 1, cx:] = 1.0
    d = distance_field(mask, w, h)

    # swoop: a slow warp of the distance field, stronger far from the mark
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = d + 60 * s * np.sin(xx / w * 5.0 + yy / h * 2.0) * np.clip(d / (500 * s), 0, 1)

    bw = 92 * s                                 # band width
    img = np.broadcast_to(bg, (h, w, 3)).copy()
    # paint filled regions outer -> inner, so each band only anti-aliases its outer edge (no seams)
    for b in reversed(range(BANDS)):
        cover = np.clip((b + 1) * bw - d + 0.5, 0, 1)[..., None]
        img = img * (1 - cover) + seq[b % len(seq)] * cover
    # the mark itself, in the foreground colour, crisp
    big = load_alpha(BRAND / "omarchy-logo.png", int(size * DS * s), int(size * DS * s))
    y0, x0 = int(cy * DS * s - big.shape[0] / 2), int(cx * DS * s - big.shape[1] / 2)
    img[y0:y0 + big.shape[0], x0:x0 + big.shape[1]] = (
        img[y0:y0 + big.shape[0], x0:x0 + big.shape[1]] * (1 - big[..., None]) + hex2arr(pal["foreground"]) * big[..., None])

    rng = np.random.default_rng(70)
    img *= (1 + rng.normal(0, 0.03, (h, w, 1))).astype(np.float32)
    font = str(FONTS / "SpaceMono" / "SpaceMonoNerdFontMono-Regular.ttf")
    dim = pal.get("dark_foreground", pal["foreground"])
    m = int(110 * s)
    post = ["-font", font, "-pointsize", str(max(int(24 * s), 7)), "-fill", dim, "-kerning", str(max(int(6 * s), 1)),
            "-gravity", "southwest", "-annotate", f"+{m}+{m}", f"OMARCHY  ·  GROOVY  ·  {name.upper()}"]
    save_rgb(np.clip(img, 0, 1), out_path("19-groovy", f"groovy--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
