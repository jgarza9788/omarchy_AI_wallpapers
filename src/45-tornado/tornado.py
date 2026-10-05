"""45 — Tornado: a twister touching down on the app grid.

A launcher grid of app icons lies flat on the ground, receding to the horizon under a
storm sky. A Rankine vortex has touched down. Outside its core the swirl speed falls as
1/r and the inflow spirals icons in along the ground; inside, the updraft lifts them up
a leaning funnel on helical paths. Icons tumble as they climb and leave curved motion
smears, and the funnel itself is made of dust spiralling up the same helices into the
wall cloud. Everything is projected through a perspective camera low over the ground.

The Omarchy wordmark signs the corner away from the funnel; funnel position, lean and camera azimuth are seeded from the theme name.

Usage: python3 src/45-tornado/tornado.py [--scheme omarchy|all] [--scale 0.25]
"""
import hashlib
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from appfield import APPS, CORE, Atlas, Camera, Canvas, affine, brand, finish, quantize, splat, write  # noqa: E402
from common import H, W, hex2arr, out_path, ramp, scheme_args  # noqa: E402

SCHEMES = ["omarchy", "tokyo-night", "everforest", "ristretto"]
TOP = 26.0                                       # wall-cloud height


def render(name, pal, s):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    fg = c["foreground"]
    dim = c.get("dark_foreground", fg) * 0.7 + c["background"] * 0.3
    hot = c.get("bright_foreground", fg)
    debris = [c["accent"], c.get("cyan", c["blue"]), c.get("magenta", c["red"]), c["yellow"]]

    cam = Camera(elev_deg=-rng.uniform(7, 10), azim_deg=-90 + rng.uniform(-12, 12), dist=62, w=w, h=h,
                 fov_deg=58, target=(0, 0, 15))
    base = np.array([rng.uniform(5, 14) * (1 if rng.random() < .5 else -1), rng.uniform(4, 14), 0.0])
    lean = np.array([rng.uniform(-0.5, 0.5), rng.uniform(0.1, 0.4)])

    def axis(z):
        z = np.asarray(z, float)
        return base[0] + lean[0] * z ** 1.35 / 3, base[1] + lean[1] * z ** 1.35 / 3

    def radius(z):
        return 0.9 + 0.08 * z + 0.006 * z ** 2.2

    def helix(theta, z, rfac=1.0):
        ax, ay = axis(z)
        r = radius(z) * rfac
        return np.stack([ax + r * np.cos(theta), ay + r * np.sin(theta), z], -1)

    atlas = Atlas()
    canvas = Canvas(w, h)
    light = np.zeros((h, w, 3), np.float32)
    yy = np.arange(h, dtype=np.float32)[:, None]
    hx, hy, _ = cam.project(np.array([0.0, 400.0, 0.0]))
    # a pale band of light under the storm, along the horizon
    light += (c["accent"] * 0.25 + fg * 0.15) * np.exp(-((yy - hy) / (h * 0.05)) ** 2)[..., None] * 0.35
    light += c.get("magenta", c["red"]) * np.exp(-((yy - hy + h * 0.06) / (h * 0.09)) ** 2)[..., None] * 0.06

    # --- ground icons: a flat grid receding to the horizon; near the funnel they spiral inward
    pitch = 2.2
    gx, gy = np.meshgrid(np.arange(-110, 110, pitch), np.arange(-30, 150, pitch))
    g = np.stack([gx.ravel(), gy.ravel(), np.zeros(gx.size)], 1)
    rel = g[:, :2] - base[:2]
    d = np.linalg.norm(rel, axis=1)
    keep = d > 2.6
    swirl = np.clip(9.0 / np.maximum(d, 1), 0, 1.2) * np.exp(-d / 30)                       # angular drag ∝ 1/r
    pull = np.clip(1 - 2.2 / np.maximum(d, 1e-3), 0.4, 1) ** np.clip(6 / d, 0, 3)
    ang = np.arctan2(rel[:, 1], rel[:, 0]) + swirl
    g[:, :2] = base[:2] + np.stack([np.cos(ang), np.sin(ang)], 1) * (d * pull)[:, None]
    gl = np.array([APPS[i % len(APPS)] for i in rng.permutation(len(g))])
    xs, ys, dep = cam.project(g)
    order = np.argsort(-dep)
    for i in order:
        if not keep[i] or dep[i] < 3 or not (-80 < xs[i] < w + 80 and ys[i] < h + 80):
            continue
        px = 1.7 * cam.f / dep[i]
        if px < 3:
            continue
        flat = 0.25 + 0.75 * (cam.pos[2] / dep[i]) ** 0.5                     # foreshortened on the ground
        stir = math.exp(-d[i] / 7)
        col = dim * (1 - stir) + c["accent"] * stir * 0.7 + dim * stir * 0.3
        fade = np.clip((ys[i] - hy) / (h * 0.06), 0, 1) * (0.25 + 0.4 * math.exp(-dep[i] / 60)) + stir * 0.3
        A = affine(angle=float(swirl[i] * 0.8 * stir * 3), squash=min(flat * 1.4, 1))
        canvas.stamp(atlas.get(int(gl[i]), quantize(px, s)), xs[i], ys[i], col, alpha=0.85 * fade, A=A)

    # --- the funnel: dust spiralling up the helices into the wall cloud
    n = 900000
    z = TOP * rng.random(n) ** 1.25
    th = rng.uniform(0, 2 * np.pi, n) + z * 0.9
    rf = 1 + np.abs(rng.normal(0, 0.18, n)) * (1 + z / 10)
    p = helix(th, z, rf)
    px_, py_, pd = cam.project(p)
    side = np.cos(th - math.radians(-90 + 90))                              # lit side brighter
    shade = 0.55 + 0.45 * np.clip(np.sin(th) * -1, -1, 1)
    col = ramp([c["background"] * 0.5 + fg * 0.5, fg, hot], np.clip(z / TOP * 0.6 + 0.3 * shade, 0, 1))
    splat(light, px_, py_, col, (0.012 * 16 * s * s * shade * (1.2 - z / TOP * 0.4)).astype(np.float32))
    del side
    # debris skirt at the base: a low, wide spinning ring of dust
    n = 300000
    rr = 1.5 + rng.exponential(2.2, n)
    th = rng.uniform(0, 2 * np.pi, n)
    zz = np.abs(rng.normal(0, 0.6, n)) * np.exp(-(rr - 1.5) / 6) * 2
    p = np.stack([base[0] + rr * np.cos(th), base[1] + rr * np.sin(th), zz], 1)
    px_, py_, _ = cam.project(p)
    splat(light, px_, py_, fg * 0.7 + c["accent"] * 0.3, np.full(n, 0.003 * 16 * s * s, np.float32))
    # wall cloud: a broad, slowly rotating disc of darker-lit cloud at the top
    n = 700000
    rr = np.sqrt(rng.random(n)) * 34
    th = rng.uniform(0, 2 * np.pi, n) + rr * 0.06
    zz = TOP + rng.normal(0, 1.2, n) + rr * 0.08
    ax, ay = axis(TOP)
    p = np.stack([ax + rr * np.cos(th), ay + rr * 0.6 * np.sin(th), zz], 1)
    px_, py_, _ = cam.project(p)
    splat(light, px_, py_, fg * 0.6 + c["accent"] * 0.1, (0.02 * 16 * s * s * np.exp(-rr / 18)).astype(np.float32))

    # --- lifted icons: on helices up the funnel, tumbling, each with a curved smear behind it
    m = 200
    zt = TOP * 0.95 * rng.random(m) ** 0.8
    th0 = rng.uniform(0, 2 * np.pi, m)
    rfi = 1.05 + rng.exponential(0.35, m)
    heads = helix(th0 + zt * 0.9, zt, rfi)
    hxp, hyp, hdp = cam.project(heads)
    lifted = [APPS[i % len(APPS)] for i in rng.permutation(m)]
    for i in rng.choice(m, 8, replace=False):
        lifted[i] = CORE[i % len(CORE)]
    order = np.argsort(-hdp)
    for i in order:
        k = np.linspace(0, 1, 140)
        dz = min(zt[i], 2.5 + zt[i] * 0.15)
        tz = zt[i] - dz * (1 - k)
        tth = th0[i] + tz * 0.9 - (1 - k) * 1.6
        tp = helix(tth, tz, rfi[i])
        tx, ty, _ = cam.project(tp)
        col = debris[i % len(debris)] * 0.7 + hot * 0.3
        splat(light, tx, ty, col, (0.06 * k ** 2).astype(np.float32))
        front = math.sin(th0[i] + zt[i] * 0.9) < 0                                    # in front of the funnel
        px = 1.5 * cam.f / hdp[i]
        v = np.array([tx[-1] - tx[-6], ty[-1] - ty[-6]])
        A = affine(angle=float(rng.uniform(-3, 3)), stretch=1.25, squash=0.8, axis=math.atan2(v[1], v[0]))
        canvas.stamp(atlas.get(lifted[i], quantize(px, s)), hxp[i], hyp[i], col,
                     alpha=1.0 if front else 0.55, A=A)

    light += canvas.rgb * 0.95
    img = finish(light, pal, s, bloom=0.8, exposure=1.25, vignette=0.55)
    corner = "southeast" if cam.project(base)[0] < w / 2 else "southwest"
    write(img, out_path("45-tornado", f"tornado--{name}", s), brand(pal, s, f"TORNADO  ·  {name.upper()}", corner))


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
