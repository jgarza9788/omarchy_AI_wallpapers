"""28 — Chladni: sand on a singing plate.

A metal plate is bowed into one of its resonant modes; its displacement is

    u(x, y) = cos(nπx) cos(mπy) − cos(mπx) cos(nπy)        (x, y in [0, 1])

Sand grains sitting on the plate get kicked around by the vibration: each step a
grain makes a random jump whose size is proportional to the local amplitude |u|.
Grains on the nodal lines (u = 0) stay put, so after enough steps the sand
collects into the mode's Chladni figure. The theme name is hashed to pick the
mode (n, m), like Sigils (09) picks its attractor, so every theme rings its own note.

Rendered as sand on brushed dark metal under a raking light: the grain density
becomes a height field (piles with shadows) plus individual grain sparkle.

Usage: python3 src/28-chladni/chladni.py [--scheme omarchy|all] [--scale 0.25]
"""
import hashlib
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from appfield import brand, write  # noqa: E402
from common import H, W, box_blur, hex2arr, out_path, scheme_args, value_noise  # noqa: E402

SCHEMES = ["omarchy", "kanagawa", "ristretto", "nord"]
GRAINS = 2_000_000
STEPS = 280
KICK = 42.0                       # px (4K) jump at full amplitude
F0 = 37.0                         # Hz of the (1, 0) mode, for the caption (f ∝ n² + m²)


def mode(name):
    h = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    n = 5 + h % 7                                   # 5..11
    m = 1 + (h // 7) % (n - 1)                      # 1..n-1
    if (n - m) % 2 == 0:                            # odd difference gives the classic interlocking figures
        m = m - 1 if m > 1 else m + 1
    return n, m


def amp(x, y, n, m):
    """Plate displacement at 4K pixel coords; the plate is the full screen."""
    X, Y = x / W, y / H
    return np.cos(n * np.pi * X) * np.cos(m * np.pi * Y) - np.cos(m * np.pi * X) * np.cos(n * np.pi * Y)


def render(name, pal, s):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    n, m = mode(name)

    # sand: random kicks ∝ |u|; grains settle on the nodal lines
    x = rng.uniform(0, W, GRAINS).astype(np.float32)
    y = rng.uniform(0, H, GRAINS).astype(np.float32)
    for _ in range(STEPS):
        a = np.abs(amp(x, y, n, m)).astype(np.float32) / 2
        x = np.clip(x + rng.normal(0, 1, GRAINS).astype(np.float32) * KICK * a, 0, W - 1)
        y = np.clip(y + rng.normal(0, 1, GRAINS).astype(np.float32) * KICK * a, 0, H - 1)
    settled = np.abs(amp(x, y, n, m)) / 2

    # grain density at output resolution
    xi = np.clip((x * s).astype(np.int32), 0, w - 1)
    yi = np.clip((y * s).astype(np.int32), 0, h - 1)
    dens = np.bincount(yi * w + xi, minlength=w * h).reshape(h, w).astype(np.float32) * s ** 2 * 1.8   # grains per 4K-pixel area (scale independent)
    cover = 1 - np.exp(-dens * 0.9)                       # how much sand hides the plate

    # plate: brushed dark metal with a raking light from the upper left
    brush = value_noise(h, w, max(int(3 * s), 2), rng, octaves=2)
    brush = box_blur(brush, max(int(40 * s), 1), passes=1) * 0.6 + brush * 0.4    # horizontal-ish streaks
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rake = 1 - 0.55 * np.clip((xx / w * 0.6 + yy / h * 0.8), 0, 1.2)
    metal = c.get("darker_background", c["background"]) * 0.6 + c["background"] * 0.4 + c["foreground"] * 0.05
    plate = metal[None, None] * (0.8 + 0.4 * brush[..., None]) * (0.75 + 0.5 * rake[..., None])

    # sand height -> relief shading
    height = box_blur(dens, max(int(2 * s), 1)) * 1.0
    gy, gx = np.gradient(height)
    shade = np.clip(1 + (-gx - gy) * 0.35 / max(s, 0.25), 0.45, 1.6)
    sand_c = c["yellow"] * 0.55 + c["foreground"] * 0.45
    hi = c.get("bright_foreground", c["foreground"])
    sparkle = rng.random((h, w)).astype(np.float32) ** 12 * cover
    sand = sand_c[None, None] * shade[..., None] * (0.85 + 0.3 * rake[..., None]) + hi * sparkle[..., None] * 0.6

    # soft contact shadow under the sand, offset away from the light
    sh = np.roll(np.roll(box_blur(cover, max(int(6 * s), 1)), int(5 * s), 0), int(4 * s), 1)
    img = plate * (1 - 0.6 * sh[..., None]) * (1 - cover[..., None]) + sand * cover[..., None]

    # a faint accent glint along the nodal lines where the sand is thinnest
    nodal = np.exp(-(amp(xx / s, yy / s, n, m) / 0.03) ** 2) * (1 - cover)
    img += c["accent"] * nodal[..., None] * 0.08

    f = F0 * (n * n + m * m)
    post = brand(pal, s, f"CHLADNI  ·  MODE ({n},{m})  ·  {f:,.0f} HZ  ·  {GRAINS // 1000}K GRAINS  ·  {name.upper()}")
    print(f"{name}: mode ({n},{m}), {float((settled < 0.05).mean()):.0%} of grains on a nodal line")
    write(np.clip(img, 0, 1), out_path("28-chladni", f"chladni--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
