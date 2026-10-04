"""17 — Lightspeed: jumping to hyperspace through a lattice of app grids.

App icons sit on a 3D lattice of stacked grids ahead of the camera. The camera
lurches forward, and every icon smears radially away from the vanishing point.
Each streak runs from where the icon was a moment ago to where it is now, so
nearer icons streak longer (∝ speed/depth²). The closest icons stay legible
but are stretched along their streak. Colour shifts from the theme accent at the
centre to hot hues at the edges, and the Omarchy mark is a pinpoint at the
vanishing point.

Inspired by the toplist's hyperspace starbursts and speed streaks.

Usage: python3 src/17-lightspeed/lightspeed.py [--scheme hackerman|all] [--scale 0.25]
"""
import hashlib
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from appfield import APPS, CORE, Atlas, Canvas, affine, brand, finish, quantize, splat, write  # noqa: E402
from common import BRAND, H, W, box_blur, hex2arr, load_alpha, out_path, ramp, scheme_args  # noqa: E402

SCHEMES = ["hackerman", "tokyo-night", "retro-82", "lumon"]


def render(name, pal, s):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    hot = c.get("bright_foreground", c["foreground"])
    hues = [c["accent"], c["cyan"], c["blue"], c["magenta"], c.get("orange", c["red"])]

    # lattice of grids: x, y on a unit grid, stacked in depth
    g = np.arange(-14, 15) + 0.5                  # half-cell offset: no rows on the axis
    xs, ys, zs = np.meshgrid(g, g * 0.62, np.arange(1.5, 70, 2.2), indexing="ij")
    P = np.stack([xs.ravel(), ys.ravel(), zs.ravel()], 1).astype(np.float64)
    P[:, :2] += rng.normal(0, 0.04, (len(P), 2))
    P[:, 2] += rng.uniform(0, 2.2, len(P))
    tunnel = np.hypot(P[:, 0], P[:, 1] / 0.62) > rng.uniform(2.2, 3.4)   # a clear tunnel to fly down
    P = P[tunnel & (rng.random(len(P)) < 0.3)]
    vp = np.array([w * rng.uniform(0.46, 0.56), h * rng.uniform(0.44, 0.54)])   # vanishing point
    f = w * 0.55
    speed = rng.uniform(5.5, 8.0)

    def proj(p):
        return vp[0] + f * p[:, 0] / p[:, 2], vp[1] + f * p[:, 1] / p[:, 2]

    x1, y1 = proj(P)
    prev = P.copy()
    prev[:, 2] += speed
    x0, y0 = proj(prev)
    ok = (P[:, 2] > 0.6) & (((x1 > -200) & (x1 < w + 200) & (y1 > -200) & (y1 < h + 200)) | ((x0 > 0) & (x0 < w) & (y0 > 0) & (y0 < h)))
    P, x0, y0, x1, y1 = P[ok], x0[ok], y0[ok], x1[ok], y1[ok]

    rad = np.hypot(x1 - vp[0], y1 - vp[1]) / (0.6 * w)
    col = ramp(hues, np.clip(rad, 0, 1))
    near = np.clip(3.0 / P[:, 2], 0, 1)
    light = np.zeros((h, w, 3), np.float32)

    # streaks: sampled densely, brightening toward the head
    n_t = 48
    t = np.linspace(0, 1, n_t, dtype=np.float32)[:, None]
    sx = x0[None] * (1 - t) + x1[None] * t
    sy = y0[None] * (1 - t) + y1[None] * t
    length = np.hypot(x1 - x0, y1 - y0) + 1
    wgt = (t ** 2.2) * (0.6 + 2.2 * near)[None] * np.clip(60 * s / length, 0.02, 1)[None] * 1.2
    splat(light, sx.ravel(), sy.ravel(), np.tile(col, (n_t, 1)), wgt.ravel())

    # legible icons for the nearer lattice points, stretched along their streak
    atlas = Atlas()
    canvas = Canvas(w, h)
    idx = np.nonzero(((P[:, 2] < 9) & (rng.random(len(P)) < 0.45)) | ((P[:, 2] < 16) & (rng.random(len(P)) < 0.12)))[0]
    idx = idx[np.argsort(-P[idx, 2])]
    for i in idx:
        px = quantize(0.36 * f / P[i, 2], s)
        if px < 6 or px > 260 * s:
            continue
        ang = math.atan2(y1[i] - vp[1], x1[i] - vp[0])
        stretch = 1 + min(length[i] / (px * 3.5), 2.5)
        glyph = CORE[rng.integers(len(CORE))] if rng.random() < 0.12 else APPS[rng.integers(len(APPS))]
        canvas.stamp(atlas.get(glyph, px), x1[i], y1[i], col[i] * 0.5 + hot * 0.5,
                     alpha=float(0.5 + 0.5 * near[i]), A=affine(stretch=stretch, squash=0.9, axis=ang))
    light += canvas.rgb * 1.2

    # vanishing point: a tiny blinding Omarchy mark
    size = max(int(36 * s), 6)
    mark = load_alpha(BRAND / "omarchy-logo.png", size, size)
    core = np.zeros((h, w), np.float32)
    x0c, y0c = int(vp[0] - size / 2), int(vp[1] - size / 2)
    core[y0c:y0c + size, x0c:x0c + size] = mark
    light += hot * core[..., None] * 3 + c["accent"] * box_blur(core, 120 * s)[..., None] * 14

    img = finish(light, pal, s, bloom=1.2, exposure=1.15, vignette=0.55)
    post = brand(pal, s, f"LIGHTSPEED  ·  {len(P)} APPS  ·  {name.upper()}")
    write(img, out_path("17-lightspeed", f"lightspeed--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
