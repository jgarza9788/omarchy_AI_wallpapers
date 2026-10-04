"""14 — Collapse: an app grid the moment gravity wins.

A tidy launcher grid of Nerd Font app icons. A mass has appeared (the Omarchy mark,
shrunk to a glowing singularity). Each icon breaks loose once it has been exposed
long enough, which happens sooner the closer it is (t_release ∝ d^1.5). After that
it free-falls on an integrated Newtonian orbit with a little tangential velocity,
so the infall spirals. Freed icons are drawn as long-exposure motion smears that get
hotter with speed. Icons still in their slots only lean and tilt toward the mass.
Icons that crossed the horizon feed the glow.

Inspired by the toplist's single-hue speed smears and huge negative space.

Usage: python3 src/14-collapse/collapse.py [--scheme ristretto|all] [--scale 0.25]
"""
import hashlib
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from appfield import APPS, CORE, Atlas, Canvas, affine, brand, finish, quantize, splat, write  # noqa: E402
from common import BRAND, H, W, box_blur, hex2arr, load_alpha, out_path, ramp, scheme_args  # noqa: E402

SCHEMES = ["ristretto", "nord", "hackerman", "gruvbox"]
COLS, ROWS, PITCH = 26, 13, 132          # grid in 4K pixels
GM, SOFT, T, STEPS = 1.6e8, 45.0, 1.0, 600


def simulate(p0, mass, rng):
    """Integrate released icons; returns final positions, history (STEPS//6 x N x 2), absorbed mask, speed."""
    d0 = np.linalg.norm(p0 - mass, axis=1)
    t_rel = (d0 / 1050.0) ** 2.2 * 1.0 + rng.normal(0, 0.04, len(p0))
    pos, vel = p0.copy(), np.zeros_like(p0)
    radial = (p0 - mass) / d0[:, None]
    tangent = np.stack([-radial[:, 1], radial[:, 0]], 1)
    kick = np.sqrt(GM / d0) * 0.32
    absorbed = np.zeros(len(p0), bool)
    started = np.zeros(len(p0), bool)
    hist = []
    dt = T / STEPS
    for k in range(STEPS):
        t = k * dt
        newly = (~started) & (t >= t_rel)
        vel[newly] = tangent[newly] * kick[newly, None]
        started |= newly
        act = started & ~absorbed
        r = pos[act] - mass
        d2 = (r ** 2).sum(1) + SOFT ** 2
        acc = -GM * r / d2[:, None] ** 1.5
        vel[act] += acc * dt
        pos[act] += vel[act] * dt
        absorbed |= act & (np.linalg.norm(pos - mass, axis=1) < 28)
        if k % 6 == 0:
            hist.append(pos.copy())
    speed = np.linalg.norm(vel, axis=1)
    return pos, np.array(hist), absorbed, started, speed


def render(name, pal, s):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    hot = c.get("bright_foreground", c["foreground"])
    cool = c.get("dark_foreground", c["foreground"]) * 0.8 + c["background"] * 0.2
    fire = [c["accent"], c.get("orange", c["red"]), c["yellow"], hot]

    gx = (np.arange(COLS) - (COLS - 1) / 2) * PITCH + W / 2
    gy = (np.arange(ROWS) - (ROWS - 1) / 2) * PITCH + H / 2
    p0 = np.stack(np.meshgrid(gx, gy), -1).reshape(-1, 2).astype(np.float64)
    mass = np.array([W * rng.uniform(0.6, 0.72), H * rng.uniform(0.36, 0.5)])
    pos, hist, absorbed, started, speed = simulate(p0, mass, rng)

    atlas = Atlas()
    canvas = Canvas(w, h)
    light = np.zeros((h, w, 3), np.float32)
    glyphs = [APPS[i % len(APPS)] for i in rng.permutation(len(p0))]
    icon_px = quantize(64 * s, s)
    vmax = np.percentile(speed[started & ~absorbed], 95) if (started & ~absorbed).any() else 1

    # 1. icons still in their slots: tidal lean + tilt, muted
    for i in np.nonzero(~started)[0]:
        r = mass - p0[i]
        d = np.linalg.norm(r)
        lean = r / d * min(2.2e6 / d ** 2, 40)
        tilt = min(1.8e5 / d ** 2, 0.5) * math.copysign(1, r[0])
        x, y = (p0[i] + lean) * s
        canvas.stamp(atlas.get(glyphs[i], icon_px), x, y, cool, alpha=0.85, A=affine(angle=tilt))

    # 2. freed icons: long-exposure smear along the integrated path, hotter with speed
    for i in np.nonzero(started & ~absorbed)[0]:
        path = hist[:, i] * s
        moved = np.linalg.norm(np.diff(path, axis=0), axis=1) > 0.05
        if moved.sum() < 2:
            continue
        path = path[np.argmax(moved):]
        heat = float(np.clip(speed[i] / vmax, 0, 1))
        col = ramp(fire, np.array([0.25 + 0.75 * heat]))[0]
        # the smear: dense additive splats along the path, brightening toward the icon
        seg = np.linspace(0, 1, len(path))
        fine = np.linspace(0, len(path) - 1, len(path) * 8)
        fx = np.interp(fine, np.arange(len(path)), path[:, 0])
        fy = np.interp(fine, np.arange(len(path)), path[:, 1])
        wgt = (fine / fine.max()) ** 2.0 * (0.3 + 0.7 * heat)
        splat(light, fx, fy, col, wgt.astype(np.float32))
        v = path[-1] - path[-2]
        ang = math.atan2(v[1], v[0])
        A = affine(angle=float(rng.uniform(-1, 1) * heat * 2.5), stretch=1 + 1.6 * heat, squash=1 - 0.3 * heat, axis=ang)
        canvas.stamp(atlas.get(glyphs[i], icon_px), path[-1, 0], path[-1, 1], col * 0.8 + hot * 0.2,
                     alpha=1.0, A=A)

    # 3. the singularity: the Omarchy mark, tiny and blinding, with an accretion swirl
    mx, my = mass * s
    n_abs = int(absorbed.sum())
    th = rng.uniform(0, 2 * np.pi, 40000)
    rr = rng.exponential(55, 40000) * s + 10 * s
    swirl = th + 3.0 / (rr / (40 * s))
    splat(light, mx + rr * np.cos(swirl), my + rr * np.sin(swirl) * 0.85, ramp(fire, np.clip(1 - rr / (220 * s), 0, 1)),
          np.full(40000, 0.03 + 0.002 * n_abs, np.float32))
    core_px = max(int(44 * s), 6)
    mark = load_alpha(BRAND / "omarchy-logo.png", core_px, core_px)
    core = np.zeros((h, w), np.float32)
    x0, y0 = int(mx - core_px / 2), int(my - core_px / 2)
    core[y0:y0 + core_px, x0:x0 + core_px] = mark
    light += hot * core[..., None] * 3 + c["accent"] * box_blur(core, 30 * s)[..., None] * 25

    light += canvas.rgb * 1.0
    img = finish(light, pal, s, bloom=1.0, exposure=1.2, vignette=0.45)
    post = brand(pal, s, f"COLLAPSE  ·  {int(started.sum())} APPS FALLING  ·  {n_abs} LOST  ·  {name.upper()}")
    write(img, out_path("14-collapse", f"collapse--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
