"""16 — Merger: two app galaxies collide (a Toomre & Toomre restricted N-body sim).

Galaxy A is "system" (Arch, Linux, Hyprland, terminal glyphs, cool colours) and
galaxy B is "apps" (warm colours). Their cores fall past each other on a
parabolic orbit; each carries a disk of massless test particles on circular orbits,
tilted at its own angle (seeded by the theme name). Everything is integrated with
leapfrog in softened point-mass potentials, and the snapshot is taken after
pericentre, when tidal tails and a bridge have flung icons between the two.
Dust particles are splatted as glowing gas and a subset are drawn as icons.

Usage: python3 src/16-merger/merger.py [--scheme tokyo-night|all] [--scale 0.25]
"""
import hashlib
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from appfield import APPS, CORE, Atlas, Camera, Canvas, brand, finish, quantize, splat, write  # noqa: E402
from common import BRAND, H, W, box_blur, hex2arr, load_alpha, out_path, ramp, scheme_args  # noqa: E402

SCHEMES = ["tokyo-night", "ethereal", "everforest", "kanagawa"]
M1, M2, EPS, RP = 1.0, 1.0, 0.12, 1.25


def rot(incl, peri):
    ci, si, cp, sp = math.cos(incl), math.sin(incl), math.cos(peri), math.sin(peri)
    Rx = np.array([[1, 0, 0], [0, ci, -si], [0, si, ci]])
    Rz = np.array([[cp, -sp, 0], [sp, cp, 0], [0, 0, 1]])
    return Rz @ Rx


def disk(rng, n, mass, incl, peri, spin):
    r = rng.uniform(0.18, 1.15, n)
    phi = rng.uniform(0, 2 * np.pi, n)
    pos = np.stack([r * np.cos(phi), r * np.sin(phi), rng.normal(0, 0.015, n)], 1)
    v = np.sqrt(mass * r * r / (r * r + EPS * EPS) ** 1.5)
    vel = np.stack([-np.sin(phi), np.cos(phi), np.zeros(n)], 1) * (v * spin)[:, None]
    R = rot(incl, peri)
    return pos @ R.T, vel @ R.T, r


def simulate(rng, t_after):
    """Return core positions and particle positions/ids at t_peri + t_after."""
    Mt = M1 + M2
    p = 2 * RP
    th0 = -math.acos(2 * RP / 6.0 - 1)                    # start at separation 6 on a parabola
    rel = 6.0 * np.array([math.cos(th0), math.sin(th0), 0.0])
    k = math.sqrt(Mt / p)
    vrel = k * (math.sin(th0) * rel / 6.0 + (1 + math.cos(th0)) * np.array([-math.sin(th0), math.cos(th0), 0.0]))
    D = math.tan(th0 / 2)
    t_peri = -math.sqrt(p ** 3 / Mt) / 2 * (D + D ** 3 / 3)
    c1, c2 = -M2 / Mt * rel, M1 / Mt * rel
    v1, v2 = -M2 / Mt * vrel, M1 / Mt * vrel

    na, nb = 9000, 9000
    pa, va, ra = disk(rng, na, M1, rng.uniform(0, 0.6), rng.uniform(0, 6.28), 1)
    pb, vb, rb = disk(rng, nb, M2, rng.uniform(0.6, 1.6), rng.uniform(0, 6.28), rng.choice([1, -1]))
    P = np.concatenate([pa + c1, pb + c2])
    V = np.concatenate([va + v1, vb + v2])
    gal = np.concatenate([np.zeros(na, int), np.ones(nb, int)])
    radius = np.concatenate([ra, rb])

    def accel(x, a1, a2):
        out = np.zeros_like(x)
        for c, m in ((a1, M1), (a2, M2)):
            d = x - c
            out -= m * d / ((d * d).sum(-1, keepdims=True) + EPS * EPS) ** 1.5
        return out

    dt = 0.004
    steps = int((t_peri + t_after) / dt)
    for _ in range(steps):
        d = c2 - c1
        f = d / ((d @ d) + EPS * EPS) ** 1.5
        v1 += 0.5 * dt * M2 * f
        v2 -= 0.5 * dt * M1 * f
        V += 0.5 * dt * accel(P, c1, c2)
        c1 = c1 + dt * v1
        c2 = c2 + dt * v2
        P += dt * V
        d = c2 - c1
        f = d / ((d @ d) + EPS * EPS) ** 1.5
        v1 += 0.5 * dt * M2 * f
        v2 -= 0.5 * dt * M1 * f
        V += 0.5 * dt * accel(P, c1, c2)
    return c1, c2, P, gal, radius


def render(name, pal, s):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    hot = c.get("bright_foreground", c["foreground"])
    cool = [hot, c["cyan"], c["accent"], c["blue"]]
    warm = [hot, c["yellow"], c.get("orange", c["red"]), c["magenta"]]

    c1, c2, P, gal, radius = simulate(rng, t_after=rng.uniform(2.6, 4.2))
    cam = Camera(elev_deg=rng.uniform(25, 60), azim_deg=rng.uniform(0, 360), dist=30, w=w, h=h, fov_deg=30,
                 target=(c1 + c2) / 2)
    x, y, d = cam.project(P)
    # fit the scene (2nd-98th percentile) into the frame
    lo_x, hi_x = np.percentile(x, [1.5, 98.5])
    lo_y, hi_y = np.percentile(y, [1.5, 98.5])
    k = min(0.86 * w / (hi_x - lo_x), 0.8 * h / (hi_y - lo_y))
    mx, my = (lo_x + hi_x) / 2, (lo_y + hi_y) / 2

    def fit(xx, yy):
        return w / 2 + (xx - mx) * k, h / 2 + (yy - my) * k

    X, Y = fit(x, y)
    light = np.zeros((h, w, 3), np.float32)
    t = np.clip((radius - 0.18) / 0.97, 0, 1)
    col = np.where(gal[:, None] == 0, ramp(cool, t), ramp(warm, t))
    splat(light, X, Y, col, np.full(len(X), 0.45 * (1.5 / max(s, 0.3)) ** 0.5, np.float32))
    neb = np.zeros_like(light)
    splat(neb, X, Y, col, np.full(len(X), 1.0, np.float32))
    light += np.stack([box_blur(neb[..., i], 26 * s) for i in range(3)], -1) * 1.5

    # icons: a subset of particles, depth sorted
    atlas = Atlas()
    canvas = Canvas(w, h)
    idx = rng.choice(len(P), int(1300 * min(1, 0.5 + s)), replace=False)
    idx = idx[np.argsort(-d[idx])]
    dmed = np.median(d)
    for i in idx:
        glyph = CORE[rng.integers(len(CORE))] if gal[i] == 0 else APPS[rng.integers(len(APPS))]
        px = quantize(34 * s * (dmed / d[i]) ** 1.5 * rng.uniform(0.7, 1.3), s)
        if px < 5:
            continue
        canvas.stamp(atlas.get(glyph, px), X[i], Y[i], col[i] * 0.6 + hot * 0.4, alpha=0.95)
    light += canvas.rgb * 1.1

    # the two cores
    for cpos, base in ((c1, cool), (c2, warm)):
        cx, cy, _ = cam.project(cpos[None])
        cx, cy = fit(cx, cy)
        core = np.zeros((h, w), np.float32)
        size = max(int(70 * s), 8)
        mark = load_alpha(BRAND / "omarchy-logo.png", size, size)
        x0, y0 = int(cx[0] - size / 2), int(cy[0] - size / 2)
        if 0 <= x0 < w - size and 0 <= y0 < h - size:
            core[y0:y0 + size, x0:x0 + size] = mark
        light += hot * core[..., None] * 2 + base[1] * box_blur(core, 90 * s)[..., None] * 30

    img = finish(light, pal, s, bloom=1.1, exposure=1.15, vignette=0.45)
    post = brand(pal, s, f"MERGER  ·  SYSTEM × APPS  ·  {name.upper()}")
    write(img, out_path("16-merger", f"merger--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
