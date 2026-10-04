"""02 — Topography: a contour map where the Omarchy wordmark rises as a plateau.

Pure numpy: fBm terrain + blurred wordmark mesa, contour lines drawn with a
constant pixel width (level distance / gradient magnitude), hypsometric line
colours from the theme's ANSI palette, faint hillshade, and map-style labels in
Iosevka Nerd Font.

Usage: python3 src/02-topography/topography.py [--scheme everforest|all] [--scale 0.25]
"""
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import (BRAND, FONTS, H, W, box_blur, out_path, hex2arr, load_alpha, ramp,  # noqa: E402
                    save_rgb, scheme_args, smoothstep, value_noise)

SCHEMES = ["everforest", "nord", "kanagawa", "catppuccin", "flexoki-light"]
LEVELS = 44


def terrain_field(w, h, s, terrain_gain=0.75, halo_gain=0.45):
    """fBm terrain with the Omarchy wordmark raised as a flat-topped mesa, in [0, 1].

    Shared with 22-paper-terrain."""
    rng = np.random.default_rng(7)
    terrain = value_noise(h, w, int(1400 * s), rng, octaves=5, persistence=0.42)
    terrain = (terrain - terrain.min()) / (terrain.max() - terrain.min())

    # wordmark mesa: ~58% of the width, slightly above centre
    mark = load_alpha(BRAND / "omarchy-wordmark.png", int(w * 0.58), int(h * 0.3))
    mesa = np.zeros((h, w), np.float32)
    y0, x0 = int(h * 0.33), (w - mark.shape[1]) // 2
    mesa[y0:y0 + mark.shape[0], x0:x0 + mark.shape[1]] = mark
    mesa = box_blur(mesa, 2.5 * s, passes=2)
    halo = box_blur(mesa, 120 * s)  # broad rise around the letters
    halo /= halo.max()

    field = terrain * terrain_gain * (1 - mesa) + halo_gain * halo * (1 - mesa) + 0.95 * mesa
    return (field - field.min()) / (field.max() - field.min())


def render(name, pal, s):
    w, h = int(W * s), int(H * s)
    field = terrain_field(w, h, s)

    g = field * LEVELS
    gy, gx = np.gradient(g)
    grad = np.sqrt(gx * gx + gy * gy) + 1e-6
    frac = g - np.floor(g)
    pix = np.minimum(frac, 1 - frac) / grad          # distance to nearest contour, in px
    idx = np.round(g).astype(int)
    major = (idx % 5 == 0)
    width = np.where(major, 2.0, 0.9) * max(s * 1.6, 0.6)
    line = 1 - smoothstep(width - 0.7, width + 0.7, pix)
    alpha = np.where(major, 0.95, 0.5)

    light = pal["mode"] == "light"
    bg = hex2arr(pal["background"])
    hyps = [hex2arr(pal[k]) for k in ("blue", "cyan", "green", "yellow", "orange" if "orange" in pal else "red", "red")]
    col = ramp(hyps, field)

    # hillshade tint on the paper
    nx, ny = -gx / LEVELS * w * 0.6, -gy / LEVELS * w * 0.6
    shade = (nx * -0.6 + ny * -0.6 + 1) / np.sqrt(nx * nx + ny * ny + 1)
    shade = np.clip(shade, 0, 1.6)
    base = bg[None, None] * (1 + 0.06 * (shade[..., None] - 1) * (1 if not light else 0.6))
    # elevation wash: very faint colour by height
    base = base * 0.94 + col * 0.06

    # vignette
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    v = ((xx / w - 0.5) ** 2 + (yy / h - 0.5) ** 2 * 0.6)
    vign = 1 - (0.35 if not light else 0.08) * smoothstep(0.05, 0.4, v)
    base = base * vign[..., None]

    a = (line * alpha)[..., None]
    img = base * (1 - a) + col * a

    # map furniture: labels in Nerd Font
    fg = pal.get("dark_foreground", pal["foreground"])
    font = str(FONTS / "Iosevka" / "IosevkaNerdFontMono-Regular.ttf")
    pt = max(int(36 * s), 8)
    m = int(110 * s)
    post = [
        "-font", font, "-pointsize", str(pt), "-fill", fg,
        "-gravity", "southwest", "-annotate", f"+{m}+{m}",
        f"\U000f08c7  OMARCHY  ·  CONTOUR INTERVAL 1/{LEVELS}  ·  {name.upper()}",
        "-gravity", "northeast", "-annotate", f"+{m}+{m}", "N 34°03′  W 118°14′  \U000f0399",
        "-gravity", "southeast", "-annotate", f"+{m}+{m}", "0 ━━━━━━━━ 10 km",
    ]
    save_rgb(img, out_path("02-topography", f"topography--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for n in names:
        render(n, pals[n], scale)
