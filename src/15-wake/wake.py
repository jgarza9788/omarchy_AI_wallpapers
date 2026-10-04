"""15 — Wake: a rocket tears across the app grid.

A Nerd Font rocket flies diagonally through a full screen of app icons. Ahead of
it the grid is perfect. Behind it the icons are displaced by:
  * the wake: a push away from the flight line that widens and fades with age
  * a Kármán vortex street: vortices shed alternately on each side of the path
    with alternating spin, which swirl icons out of their slots and tumble them
    (rotation follows the local vorticity)
Each displaced icon leaves a faint trail back to its home slot, and the exhaust
plume is turbulent glowing gas that cools from white to the theme's fire colours.

Usage: python3 src/15-wake/wake.py [--scheme retro-82|all] [--scale 0.25]
"""
import hashlib
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from appfield import APPS, ROCKET, Atlas, Canvas, affine, brand, finish, quantize, splat, write  # noqa: E402
from common import H, W, hex2arr, out_path, ramp, scheme_args  # noqa: E402

SCHEMES = ["retro-82", "catppuccin", "kanagawa", "miasma"]
PITCH = 124


def displace(p, start, u, nrm, s_rocket, vortices, frac=1.0, push_on=True):
    """Wake + vortex displacement of points p (N,2), scaled by frac in [0,1] (for trails)."""
    rel = p - start
    along = rel @ u
    perp = rel @ nrm
    age = np.clip(s_rocket - along, 0, None)                    # how long ago the rocket passed
    behind = along < s_rocket
    sigma = 70 + 0.12 * age
    push = 170 * np.exp(-perp ** 2 / (2 * sigma ** 2)) * np.exp(-age / 2200) * np.sign(perp + 1e-6)
    q = p + (push * behind * frac * push_on)[:, None] * nrm
    spin = np.zeros(len(p))
    for c, gamma, R in vortices:                                 # rotate around each vortex
        r = q - c
        d2 = (r ** 2).sum(1)
        theta = gamma * np.exp(-d2 / (R * R)) * frac
        ct, st = np.cos(theta), np.sin(theta)
        q = c + np.stack([r[:, 0] * ct - r[:, 1] * st, r[:, 0] * st + r[:, 1] * ct], 1)
        spin += theta
    return q, spin, behind


def render(name, pal, s):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    hot = c.get("bright_foreground", c["foreground"])
    muted = c.get("dark_foreground", c["foreground"]) * 0.75 + c["background"] * 0.25
    fire = [hot, c["yellow"], c.get("orange", c["red"]), c["red"], c["magenta"]]

    # flight line: bottom-left -> top-right, rocket ~60% of the way
    start = np.array([-300.0, H * rng.uniform(0.95, 1.1)])
    end = np.array([W + 300.0, H * rng.uniform(-0.1, 0.1)])
    u = (end - start) / np.linalg.norm(end - start)
    nrm = np.array([-u[1], u[0]])
    L = np.linalg.norm(end - start)
    s_rocket = L * rng.uniform(0.58, 0.66)
    rocket = start + u * s_rocket

    # Kármán vortex street behind the rocket
    vortices = []
    lam, off = 380.0, 110.0
    k = 1
    while k * lam < s_rocket + 300:
        side = 1 if k % 2 else -1
        age = k * lam
        cpos = rocket - u * age + nrm * side * (off + 0.08 * age)
        vortices.append((cpos, side * 1.4 * math.exp(-age / 3000), 170 + 0.08 * age))
        k += 1

    # the grid
    gx = np.arange(PITCH / 2, W, PITCH)
    gy = np.arange(PITCH / 2, H, PITCH)
    p0 = np.stack(np.meshgrid(gx, gy), -1).reshape(-1, 2).astype(np.float64)
    p1, spin, behind = displace(p0, start, u, nrm, s_rocket, vortices)
    moved = np.linalg.norm(p1 - p0, axis=1)

    atlas = Atlas()
    canvas = Canvas(w, h)
    light = np.zeros((h, w, 3), np.float32)
    icon_px = quantize(58 * s, s)
    glyphs = [APPS[i] for i in rng.integers(0, len(APPS), len(p0))]

    # exhaust plume: turbulent gas along the path behind the rocket, cooling with age
    n = int(400000 * max(s, 0.3))
    age = rng.exponential(900, n)
    age = age[age < s_rocket + 200]
    spread = 4 + 0.06 * age
    base = rocket - u[None] * (age[:, None] + 40) + nrm[None] * rng.normal(0, 1, (age.size, 1)) * spread[:, None]
    gas, _, _ = displace(base, start, u, nrm, s_rocket, vortices, frac=0.5, push_on=False)
    heat = np.clip(age / 2600, 0, 1) ** 0.5
    weight = np.exp(-age / 1800) * 0.08 * (2 / max(s, 0.3)) ** 0.5
    splat(light, gas[:, 0] * s, gas[:, 1] * s, ramp(fire, heat), weight.astype(np.float32))

    # icons: undisturbed first, then displaced (with trails home), far from the line first
    order = np.argsort(moved)
    for i in order:
        g = atlas.get(glyphs[i], icon_px)
        m = moved[i]
        if m < 4:
            canvas.stamp(g, p0[i, 0] * s, p0[i, 1] * s, muted, alpha=0.8)
            continue
        agitation = float(np.clip(m / 260, 0, 1))
        col = muted * (1 - agitation) + (c["accent"] * 0.6 + hot * 0.4) * agitation
        fracs = np.linspace(0, 1, 9)
        path = np.array([displace(p0[i:i + 1], start, u, nrm, s_rocket, vortices, f)[0][0] for f in fracs])
        splat(light, np.interp(np.linspace(0, 8, 64), np.arange(9), path[:, 0]) * s,
              np.interp(np.linspace(0, 8, 64), np.arange(9), path[:, 1]) * s, col,
              np.full(64, 0.05 * agitation, np.float32))
        A = affine(angle=float(spin[i]) * 1.7 + float(rng.normal(0, 0.4)) * agitation)
        canvas.stamp(g, p1[i, 0] * s, p1[i, 1] * s, col, alpha=0.75 + 0.25 * agitation, A=A)

    # the rocket (fa-rocket points up-right, i.e. -45° in screen space)
    ang = math.atan2(u[1], u[0]) - math.radians(-45)
    rk = atlas.get(ROCKET, quantize(220 * s, s))
    canvas.stamp(rk, rocket[0] * s, rocket[1] * s, hot, alpha=1.0, A=affine(angle=ang))
    light += canvas.rgb
    tip = rocket - u * 95
    splat(light, np.array([tip[0] * s]), np.array([tip[1] * s]), hot, np.array([60.0], np.float32))

    img = finish(light, pal, s, bloom=1.2, exposure=1.2, vignette=0.4)
    post = brand(pal, s, f"WAKE  ·  {int((moved > 4).sum())} APPS DISPLACED  ·  {name.upper()}")
    write(img, out_path("15-wake", f"wake--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
