"""30 — Caustics: the dock at the bottom of a pool.

App icons lie scattered on the tiled floor of a shallow pool. The water surface
is a linear sea: ~40 random wave trains (amplitude ∝ wavelength, so every scale
is equally steep) plus a few raindrop ring packets, all with exact analytic
slopes so the optics stay sharp. Then optics:
  * light: parallel rays from above refract at the surface (Snell, small-angle:
    the floor hit point shifts by depth·(1 − 1/n)·∇h) and are splatted onto the
    floor, where they bunch up into sharp caustic networks
  * view: looking down through the same surface, the floor (tiles and icons)
    appears displaced the other way, so the icons wobble under the ripples
Water tint is from the theme's blue/cyan; the brightest caustic cusps go accent.

Usage: python3 src/30-caustics/caustics.py [--scheme omarchy|all] [--scale 0.25]
"""
import hashlib
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from appfield import APPS, Atlas, Canvas, affine, brand, quantize, write  # noqa: E402
from common import H, W, box_blur, hex2arr, out_path, ramp, scheme_args, value_noise  # noqa: E402

SCHEMES = ["omarchy", "tokyo-night", "osaka-jade", "catppuccin"]
N_WATER = 1.33
DEPTH = 900.0                     # 4K px; scales how far the caustic light is thrown
STEEP = 0.045                     # wave steepness a·k
RING = 2.2                        # raindrop ring amplitude (4K px)


def sea(rng):
    """Random wave trains + raindrop ring packets; returns slope(x, y) -> (dh/dx, dh/dy) in 4K px."""
    n = 40
    lam = np.exp(rng.uniform(math.log(140), math.log(520), n))
    k = 2 * np.pi / lam
    th = rng.uniform(0, 2 * np.pi, n)
    kx, ky = k * np.cos(th), k * np.sin(th)
    a = STEEP / k * rng.uniform(0.5, 1.0, n)
    ph = rng.uniform(0, 2 * np.pi, n)
    rings = [(rng.uniform(0.1, 0.9) * W, rng.uniform(0.1, 0.9) * H, rng.uniform(250, 900)) for _ in range(3)]
    kr, sig = 2 * np.pi / 110, 70.0

    def slope(x, y):
        gx = np.zeros_like(x)
        gy = np.zeros_like(x)
        for i in range(n):                                   # h = a sin(k·x + φ)
            cph = a[i] * np.cos(kx[i] * x + ky[i] * y + ph[i])
            gx += cph * kx[i]
            gy += cph * ky[i]
        for cx, cy, R in rings:                              # h = A e^{-(r-R)²/2σ²} cos(k(r-R))
            dx, dy = x - cx, y - cy
            r = np.sqrt(dx * dx + dy * dy) + 1e-3
            d = r - R
            env = RING * 300 / R * np.exp(-d * d / (2 * sig * sig))
            dh = env * (-d / sig ** 2 * np.cos(kr * d) - kr * np.sin(kr * d))
            gx += dh * dx / r
            gy += dh * dy / r
        return gx, gy
    return slope


def bilinear(img, x, y):
    h, w = img.shape[:2]
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0, y0 = x.astype(np.int32), y.astype(np.int32)
    fx, fy = x - x0, y - y0
    if img.ndim == 3:
        fx, fy = fx[..., None], fy[..., None]
    return ((img[y0, x0] * (1 - fx) + img[y0, x0 + 1] * fx) * (1 - fy)
            + (img[y0 + 1, x0] * (1 - fx) + img[y0 + 1, x0 + 1] * fx) * fy)


def density(xs, ys, w, h):
    """Bilinear splat of unit-weight points into an (h, w) map, via bincount."""
    x0, y0 = np.floor(xs).astype(np.int64), np.floor(ys).astype(np.int64)
    fx, fy = xs - x0, ys - y0
    out = np.zeros(w * h, np.float64)
    for dx, dy, wt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = x0 + dx, y0 + dy
        ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
        out += np.bincount(yi[ok] * w + xi[ok], weights=wt[ok], minlength=w * h)
    return out.reshape(h, w).astype(np.float32)


def render(name, pal, s):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    hot = c.get("bright_foreground", c["foreground"])
    water = c.get("cyan", c["blue"]) * 0.5 + c["blue"] * 0.5

    slope = sea(rng)

    # floor: dark tiles with lighter grout, and app icons dropped at random angles
    tile = 160
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32) / s
    grout = np.maximum(np.exp(-((xx % tile) - 0) ** 2 / 18), np.exp(-((yy % tile) - 0) ** 2 / 18))
    base = c["background"] * 0.75 + water * 0.18
    floor = base[None, None] * (0.9 + 0.2 * value_noise(h, w, max(int(60 * s), 4), rng, 2)[..., None])
    floor = floor * (1 - 0.35 * grout[..., None]) + (c["foreground"] * 0.35) * 0.35 * grout[..., None]
    atlas = Atlas()
    canvas = Canvas(w, h)
    icon_px = quantize(150 * s, s)
    pts = []
    while len(pts) < 26:
        p = np.array([rng.uniform(0.04, 0.96) * W, rng.uniform(0.06, 0.94) * H])
        if (p[0] < 0.2 * W and p[1] > 0.8 * H) or any(np.hypot(*(p - q)) < 380 for q in pts):
            continue
        pts.append(p)
    for x, y in pts:
        g = atlas.get(APPS[rng.integers(len(APPS))], icon_px)
        canvas.stamp(g, x * s, y * s, c["foreground"] * 0.9 + water * 0.1, alpha=1.0,
                     A=affine(angle=rng.uniform(-0.6, 0.6)))
    floor = floor * (1 - canvas.a[..., None]) + canvas.rgb

    # surface slope on the output grid (per 4K px)
    gx_o, gy_o = slope(xx, yy)

    # view: the floor seen through the moving surface
    view_shift = DEPTH * 0.6 * (1 - 1 / N_WATER) * s
    seen = bilinear(floor, xx * s - gx_o * view_shift, yy * s - gy_o * view_shift)

    # light: refract parallel rays, splat where they land (2 rays per output pixel per axis)
    rr = 2
    throw = DEPTH * (1 - 1 / N_WATER)
    caus = np.zeros((h, w), np.float32)
    pad = int(120 * s) * rr                                  # rays from just off-screen light the edges too
    for r0 in range(-pad, h * rr + pad, 256):                # in row bands to bound memory
        ry, rx = np.mgrid[r0:min(r0 + 256, h * rr + pad), -pad:w * rr + pad].astype(np.float32)
        rx = (rx + rng.random(rx.shape, dtype=np.float32)) / rr / s       # jittered rays, 4K units
        ry = (ry + rng.random(ry.shape, dtype=np.float32)) / rr / s
        rgx, rgy = slope(rx, ry)
        caus += density(((rx - rgx * throw) * s).ravel(), ((ry - rgy * throw) * s).ravel(), w, h)
    caus /= rr ** 2
    caus = box_blur(caus, max(int(1.2 * s), 1), passes=1)

    # compose: ambient water light + caustic light, cusps tinted toward accent
    cl = np.clip(caus - 0.6, 0, None)
    light = 0.5 + 0.42 * caus
    tint = ramp([water, water * 0.5 + hot * 0.5, c["accent"] * 0.6 + hot * 0.4], np.clip(cl / 2, 0, 1))
    img = seen * light[..., None] * (0.7 + 0.3 * water) + tint * (cl[..., None] ** 1.3) * 0.18
    # depth haze toward the far (top) edge and a soft vignette
    vy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    img = img * (0.8 + 0.2 * vy) + water * 0.04 * (1 - vy)

    post = brand(pal, s, f"CAUSTICS  ·  {len(pts)} APPS  ·  40 WAVE TRAINS  ·  n = {N_WATER}  ·  {name.upper()}")
    write(np.clip(img, 0, 1), out_path("30-caustics", f"caustics--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
