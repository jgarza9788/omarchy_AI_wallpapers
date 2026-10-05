"""46 — Shockwave: a blast going off inside the app grid (the opposite of 14 Collapse).

A Sedov–Taylor blast wave: the shell radius grows as R ∝ t^(2/5) and sweeps almost all
the material it passes into a thin, dense shell, leaving a hot, near-empty bubble behind.
Icons ahead of the shell haven't heard about it yet and sit untouched in their slots,
except for a slight lensing bulge just in front of the front. Icons the shell has
reached are swept outward and crowd into the bright compressed ring, squashed radially
and spun, each one dragging a radial streak from its old slot. The core is still hot.

Only the Omarchy wordmark signs the corner; the blast centre, radius and tilt are seeded from the theme name.

Usage: python3 src/46-shockwave/shockwave.py [--scheme omarchy|all] [--scale 0.25]
"""
import hashlib
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from appfield import APPS, CORE, Atlas, Canvas, affine, brand, finish, quantize, splat, write  # noqa: E402
from common import H, W, hex2arr, out_path, ramp, scheme_args  # noqa: E402

SCHEMES = ["omarchy", "catppuccin", "gruvbox", "kanagawa"]
PITCH = 120


def render(name, pal, s):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    hot = c.get("bright_foreground", c["foreground"])
    cool = c.get("dark_foreground", c["foreground"]) * 0.75 + c["background"] * 0.25
    fire = [c.get("magenta", c["red"]), c["red"], c.get("orange", c["yellow"]), c["yellow"], hot]

    cols, rows = W // PITCH + 2, H // PITCH + 2
    gx = (np.arange(cols) - (cols - 1) / 2) * PITCH + W / 2
    gy = (np.arange(rows) - (rows - 1) / 2) * PITCH + H / 2
    p0 = np.stack(np.meshgrid(gx, gy), -1).reshape(-1, 2).astype(np.float64)
    centre = np.array([W * rng.uniform(0.34, 0.66), H * rng.uniform(0.38, 0.62)])
    R = H * rng.uniform(0.33, 0.4)
    squish = rng.uniform(0.86, 0.96)                    # slightly elliptical: the grid is seen a bit off-axis
    tilt = rng.uniform(-0.5, 0.5)
    ct, st = math.cos(tilt), math.sin(tilt)

    def to_local(p):
        d = p - centre
        return np.stack([d[:, 0] * ct + d[:, 1] * st, (-d[:, 0] * st + d[:, 1] * ct) / squish], 1)

    def to_screen(q):
        q = np.stack([q[:, 0], q[:, 1] * squish], 1)
        return centre + np.stack([q[:, 0] * ct - q[:, 1] * st, q[:, 0] * st + q[:, 1] * ct], 1)

    q0 = to_local(p0)
    d0 = np.linalg.norm(q0, axis=1)
    u = q0 / np.maximum(d0, 1e-6)[:, None]
    x = d0 / R                                          # fractional radius

    # where each icon ends up: swept material crowds into the shell (Sedov density ∝ x^~9 near the front)
    swept = x < 1
    d1 = d0.copy()
    d1[swept] = R * (0.80 + 0.2 * x[swept] ** 0.35 + rng.normal(0, 0.012, swept.sum()))
    lag = swept & (rng.random(len(x)) < 0.12)           # a few heavy ones lag behind as ejecta in the bubble
    d1[lag] = R * rng.uniform(0.35, 0.75, lag.sum())
    ahead = (x >= 1) & (x < 1.25)                       # lensing bulge just in front of the front
    d1[ahead] = d0[ahead] + R * 0.035 * np.exp(-((x[ahead] - 1) / 0.08) ** 2)
    p1 = to_screen(u * d1[:, None])
    heat = np.where(swept, np.clip(1.05 - (1 - x) * 0.6, 0, 1) * (0.6 + 0.4 * rng.random(len(x))), 0)

    atlas = Atlas()
    canvas = Canvas(w, h)
    light = np.zeros((h, w, 3), np.float32)
    glyphs = np.array([APPS[i % len(APPS)] for i in rng.permutation(len(p0))])
    for i in rng.choice(len(p0), 18, replace=False):
        glyphs[i] = CORE[i % len(CORE)]
    px = quantize(60 * s, s)

    # 1. the quiet grid ahead of the front (leaving the signature corner clear)
    for i in np.nonzero(~swept)[0]:
        if p1[i, 0] < 760 and p1[i, 1] > H - 330:
            continue
        near = math.exp(-((x[i] - 1) / 0.18) ** 2)
        col = cool * (1 - near) + c["accent"] * near * 0.6 + cool * near * 0.4
        canvas.stamp(atlas.get(int(glyphs[i]), px), *(p1[i] * s), col, alpha=0.8)

    # 2. streaks: every swept icon drags a radial smear from its old slot to the shell
    for i in np.nonzero(swept)[0]:
        n = int(abs(d1[i] - d0[i]) * s * 3) + 20
        t = np.linspace(0, 1, n)
        rad = (d0[i] * 0.15 + (d1[i] - d0[i] * 0.15) * t)[:, None]
        for k in range(5):                              # a few parallel strands give the streak some width
            off = np.array([-u[i, 1], u[i, 0]]) * (k - 2) * 2.2
            path = to_screen(u[i] * rad + off) * s
            col = ramp(fire, np.array([0.15 + 0.7 * heat[i]]))[0]
            splat(light, path[:, 0], path[:, 1], col, (0.11 * t ** 3 * (1 - abs(k - 2) / 3)).astype(np.float32))

    # 3. the shell: a dense ring of hot gas, thin and bright, with filaments
    n = 260000
    th = rng.uniform(0, 2 * np.pi, n)
    fil = 1 + 0.025 * np.sin(th * rng.integers(9, 15)) + 0.012 * np.sin(th * 37 + 1.3)
    rr = R * (fil - np.abs(rng.normal(0, 0.018, n)) - rng.exponential(0.02, n))
    pts = to_screen(np.stack([rr * np.cos(th), rr * np.sin(th)], 1)) * s
    tt = np.clip(rr / R, 0, 1) ** 6
    splat(light, pts[:, 0], pts[:, 1], ramp(fire, 0.15 + 0.6 * tt), np.full(n, 0.04 * 8 * s * s, np.float32) * (0.3 + tt))

    # 4. the swept icons on the shell: squashed radially, stretched along it, spun, hot
    # a thin precursor flash just ahead of the front, in the accent colour
    n = 120000
    th = rng.uniform(0, 2 * np.pi, n)
    rr = R * (1.03 + 0.025 * np.sin(th * 11) * 0 + np.abs(rng.normal(0, 0.006, n)))
    pts = to_screen(np.stack([rr * np.cos(th), rr * np.sin(th)], 1)) * s
    splat(light, pts[:, 0], pts[:, 1], c["accent"], np.full(n, 0.004 * 8 * s * s, np.float32))

    order = np.argsort(heat)
    for i in order[swept[order]]:
        ang_screen = math.atan2(*(p1[i] - centre)[::-1])
        A = affine(angle=float(rng.normal(0, 0.9 * heat[i])), stretch=1 - 0.4 * heat[i], squash=1 + 0.35 * heat[i],
                   axis=ang_screen)
        col = ramp(fire, np.array([0.45 + 0.55 * heat[i]]))[0]
        canvas.stamp(atlas.get(int(glyphs[i]), px), *(p1[i] * s), col, alpha=1.0, A=A)

    # 5. the hot bubble: a faint interior glow and a white-hot core
    n = 90000
    rr = R * np.sqrt(rng.random(n)) * 0.8
    th = rng.uniform(0, 2 * np.pi, n)
    pts = to_screen(np.stack([rr * np.cos(th), rr * np.sin(th)], 1)) * s
    splat(light, pts[:, 0], pts[:, 1], ramp(fire, 0.4 * (rr / R)), np.full(n, 0.004 * 8 * s * s, np.float32))
    rr = rng.exponential(R * 0.05, 60000)
    th = rng.uniform(0, 2 * np.pi, 60000)
    pts = to_screen(np.stack([rr * np.cos(th), rr * np.sin(th)], 1)) * s
    splat(light, pts[:, 0], pts[:, 1], ramp(fire[2:], np.clip(1 - rr / (R * 0.15), 0, 1)),
          np.full(60000, 0.1 * 8 * s * s, np.float32))

    light += canvas.rgb * 0.95
    img = finish(light, pal, s, bloom=1.1, exposure=1.15, vignette=0.5)
    write(img, out_path("46-shockwave", f"shockwave--{name}", s), brand(pal, s, f"SHOCKWAVE  ·  {name.upper()}"))


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
