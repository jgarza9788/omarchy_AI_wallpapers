"""27 — Physarum: a slime mold wires up your apps.

Jones (2010) agent model of Physarum polycephalum. Several hundred thousand agents
each carry a heading; every step they
  1. sense the chemoattractant trail at three points ahead (left / centre / right),
  2. turn toward the strongest reading (or randomly when the centre is weakest),
  3. step forward and deposit trail,
and the trail map diffuses (3x3 mean) and decays. App icons scattered over the
screen are food: agents smell them from afar (a static long-range field sensed
on top of the trail, so nothing gets trapped orbiting a source), and the mold
settles into the efficient, Tokyo-rail-like vein network that connects them. The trail map is
tone-mapped into glowing veins, with each app sitting at a network node.

The sim runs at a fixed resolution (independent of --scale), so previews match 4K.

Usage: python3 src/27-physarum/physarum.py [--scheme omarchy|all] [--scale 0.25]
"""
import hashlib
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from appfield import APPS, Atlas, Canvas, brand, finish, quantize, splat, write  # noqa: E402
from common import H, W, hex2arr, out_path, ramp, scheme_args, upsample  # noqa: E402

SCHEMES = ["omarchy", "osaka-jade", "tokyo-night", "ethereal"]
SW, SH = 1920, 1080                      # sim grid
N_AGENTS = 500_000
STEPS = 1000
SA, SD, RA, STEP = math.radians(25), 11.0, math.radians(40), 1.2
DEPOSIT, DECAY = 4.0, 0.12
FOOD_RANGE, FOOD_PULL = 120.0, 14.0


def place_food(rng, n=34):
    pts = []
    while len(pts) < n:
        p = np.array([rng.uniform(0.05, 0.95) * SW, rng.uniform(0.07, 0.93) * SH])
        if p[0] < 0.22 * SW and p[1] > 0.78 * SH:          # keep the brand corner clear
            continue
        if all(np.hypot(*(p - q)) > 180 for q in pts):
            pts.append(p)
    return np.array(pts)


def diffuse(t):
    s = t.copy()
    s += np.roll(t, 1, 0) + np.roll(t, -1, 0)
    s2 = s + np.roll(s, 1, 1) + np.roll(s, -1, 1)
    return s2 / 9


def simulate(rng, food):
    trail = np.zeros((SH, SW), np.float32)
    x = rng.uniform(0, SW, N_AGENTS).astype(np.float32)
    y = rng.uniform(0, SH, N_AGENTS).astype(np.float32)
    a = rng.uniform(0, 2 * np.pi, N_AGENTS).astype(np.float32)
    fy, fx = np.mgrid[0:SH, 0:SW].astype(np.float32)
    scent = np.zeros((SH, SW), np.float32)                # static, long-range food smell (sensed, not deposited)
    for px, py in food:
        scent += np.exp(-np.hypot(fx - px, fy - py) / FOOD_RANGE)
    scent *= FOOD_PULL

    def sense(ang):
        sx = ((x + SD * np.cos(ang)).astype(np.int32)) % SW
        sy = ((y + SD * np.sin(ang)).astype(np.int32)) % SH
        return trail[sy, sx] + scent[sy, sx]

    for step in range(STEPS):
        fl, fc, fr = sense(a - SA), sense(a), sense(a + SA)
        rnd = rng.random(N_AGENTS, dtype=np.float32)
        turn = np.where((fc >= fl) & (fc >= fr), 0.0,
                        np.where((fc < fl) & (fc < fr), np.where(rnd < 0.5, -RA, RA),
                                 np.where(fl > fr, -RA, RA)))
        a += turn.astype(np.float32) + rng.normal(0, 0.05, N_AGENTS).astype(np.float32)
        x = (x + STEP * np.cos(a)) % SW
        y = (y + STEP * np.sin(a)) % SH
        idx = np.minimum(y.astype(np.int32), SH - 1) * SW + np.minimum(x.astype(np.int32), SW - 1)
        trail += np.bincount(idx, minlength=SW * SH).reshape(SH, SW).astype(np.float32) * DEPOSIT
        trail = (0.5 * trail + 0.5 * diffuse(trail)) * (1 - DECAY)
    return trail


def render(name, pal, s):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    hot = c.get("bright_foreground", c["foreground"])
    acc = c["accent"]

    food = place_food(rng)
    trail = simulate(rng, food)
    t = np.log1p(trail / np.percentile(trail, 50))
    t /= np.percentile(t, 99.7)
    t = upsample(np.clip(t, 0, 1.5), w, h)
    veins = ramp([c["background"] * 0, c.get("blue", acc) * 0.35, acc * 0.9, hot * 1.2], np.clip(t / 1.5, 0, 1) ** 1.6)
    light = veins.astype(np.float32) * 0.9

    # apps at the food sites: a halo, then the glyph
    atlas = Atlas()
    canvas = Canvas(w, h)
    icon_px = quantize(84 * s, s)
    k = W / SW
    for i, (px, py) in enumerate(food):
        X, Y = px * k, py * k
        r = rng.normal(0, 1, (4000, 2)) * 26
        splat(light, (X + r[:, 0]) * s, (Y + r[:, 1]) * s, acc, np.float32(0.02 / max(s, 0.3) ** 0.5))
        g = atlas.get(APPS[rng.integers(len(APPS))], icon_px)
        canvas.stamp(g, X * s, Y * s, hot, alpha=1.0)
    light += canvas.rgb * 1.3

    img = finish(light, pal, s, bloom=0.45, exposure=1.3, vignette=0.35)
    post = brand(pal, s, f"PHYSARUM  ·  {N_AGENTS // 1000}K AGENTS  ·  {len(food)} APPS  ·  {STEPS} STEPS  ·  {name.upper()}")
    write(img, out_path("27-physarum", f"physarum--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
