"""06 — Suminagashi: exact mathematical paper marbling.

Marbling is a sequence of area-preserving deformations of an ink surface
(Jaffer & Lu, "Mathematical Marbling"):
  * ink drop at c, radius r pushes everything outward:  p' = c + (p-c)·sqrt(1 + r²/|p-c|²)
  * a tine stroke along direction m through b:           p' = p + m·αλ/(|d| + λ),  d = (p-b)·n
  * a wavy comb:                                          p' = p + m·A·sin(ω·(p·n) + φ)
Every operation has a closed-form inverse, so each output pixel is traced
*backwards* through the whole recipe until it lands inside the drop that coloured
it (or reaches bare paper). The recipe (drop sites, ink order, comb strokes) is
seeded from the theme name, so every colour scheme is a different marbling.

Usage: python3 src/06-suminagashi/suminagashi.py [--scheme kanagawa|all] [--scale 0.25]
"""
import hashlib
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import H, W, hex2arr, out_path, save_rgb, scheme_args  # noqa: E402

SCHEMES = ["kanagawa", "rose-pine", "osaka-jade", "catppuccin-latte", "miasma"]
SS = 2  # supersampling factor per axis


def recipe(name, pal):
    """Build the list of marbling operations (in the order they're applied)."""
    rng = np.random.default_rng(int(hashlib.sha256(name.encode()).hexdigest()[:8], 16))
    inks = [pal[k] for k in ("accent", "foreground", "red", "blue", "yellow", "cyan", "magenta", "green")]
    paper = pal["background"]
    # each theme gets a small ink set; paper-coloured drops create the classic white rings
    k = int(rng.integers(2, 5))
    chosen = list(rng.choice(inks, size=k, replace=False))
    seq = []
    for c in chosen:
        seq += [c, paper]

    ops = []
    # 1. clustered drop sites, many concentric drops each (the suminagashi rings)
    sites = int(rng.integers(3, 6))
    for _ in range(sites):
        c = np.array([rng.uniform(0.15, 0.85) * W, rng.uniform(0.2, 0.8) * H])
        n_drops = int(rng.integers(16, 34))
        base_r = rng.uniform(110, 230)
        for i in range(n_drops):
            jitter = rng.normal(0, 25, 2)
            ops.append(("drop", c + jitter, base_r * rng.uniform(0.7, 1.3), seq[i % len(seq)]))
    # a scatter of small "stone" drops
    for _ in range(int(rng.integers(40, 90))):
        ops.append(("drop", np.array([rng.uniform(0, W), rng.uniform(0, H)]),
                    rng.uniform(30, 140), seq[int(rng.integers(len(seq)))]))

    # 2. combing: a few wide waves, then fine tines, angle per theme
    angle = rng.uniform(-0.5, 0.5)
    m = np.array([np.cos(angle), np.sin(angle)])
    n = np.array([-m[1], m[0]])
    for _ in range(int(rng.integers(1, 3))):
        ops.append(("wave", m, n, rng.uniform(60, 180), 2 * np.pi / rng.uniform(500, 1400), rng.uniform(0, 6.3)))
    style = rng.choice(["tines", "chevron", "swirl"])
    if style in ("tines", "chevron"):
        spacing = rng.uniform(140, 320)
        offs = np.arange(-W, W, spacing)
        for j, o in enumerate(offs):
            sign = 1 if style == "tines" or j % 2 == 0 else -1
            ops.append(("tine", n, m, np.array([W / 2, H / 2]) + n * o, sign * rng.uniform(90, 160), rng.uniform(10, 25)))
    else:
        for _ in range(int(rng.integers(2, 4))):
            ops.append(("swirl", np.array([rng.uniform(0.2, 0.8) * W, rng.uniform(0.25, 0.75) * H]),
                        rng.uniform(1.5, 3.5) * rng.choice([-1, 1]), rng.uniform(250, 600)))
    # final gentle cross wave
    ops.append(("wave", n, m, rng.uniform(20, 50), 2 * np.pi / rng.uniform(300, 700), rng.uniform(0, 6.3)))
    return ops, paper


def trace(px, py, ops, paper):
    """Trace points backwards through the ops; return per-point colour (RGB float)."""
    col = np.tile(hex2arr(paper), (px.size, 1))
    alive = np.ones(px.size, bool)
    x, y = px.astype(np.float64).copy(), py.astype(np.float64).copy()
    for op in reversed(ops):
        idx = np.nonzero(alive)[0]
        if idx.size == 0:
            break
        ax, ay = x[idx], y[idx]
        kind = op[0]
        if kind == "drop":
            _, c, r, ink = op
            dx, dy = ax - c[0], ay - c[1]
            d2 = dx * dx + dy * dy
            inside = d2 < r * r
            col[idx[inside]] = hex2arr(ink)
            alive[idx[inside]] = False
            out = ~inside
            f = np.sqrt(1 - r * r / d2[out])
            x[idx[out]] = c[0] + dx[out] * f
            y[idx[out]] = c[1] + dy[out] * f
        elif kind == "tine":
            _, n, m, b, alpha, lam = op  # n: normal of the stroke line, m: stroke direction
            d = np.abs((ax - b[0]) * n[0] + (ay - b[1]) * n[1])
            s = alpha * lam / (d + lam)
            x[idx], y[idx] = ax - m[0] * s, ay - m[1] * s
        elif kind == "wave":
            _, m, n, amp, omega, phi = op
            s = amp * np.sin(omega * (ax * n[0] + ay * n[1]) + phi)
            x[idx], y[idx] = ax - m[0] * s, ay - m[1] * s
        elif kind == "swirl":
            _, c, strength, radius = op
            dx, dy = ax - c[0], ay - c[1]
            rr = np.sqrt(dx * dx + dy * dy)
            theta = -strength * np.exp(-(rr / radius) ** 2)  # inverse rotation
            ct, st = np.cos(theta), np.sin(theta)
            x[idx], y[idx] = c[0] + dx * ct - dy * st, c[1] + dx * st + dy * ct
    return col


def render(name, pal, s):
    ops, paper = recipe(name, pal)
    w, h = int(W * s), int(H * s)
    img = np.zeros((h, w, 3), np.float32)
    rows = max(1, 200000 // (w * SS))  # output rows per chunk
    sub = (np.arange(SS) + 0.5) / SS
    for y0 in range(0, h, rows):
        y1 = min(h, y0 + rows)
        yy, xx = np.mgrid[y0:y1, 0:w].astype(np.float64)
        acc = np.zeros((y1 - y0, w, 3), np.float64)
        for oy in sub:
            for ox in sub:
                px, py = (xx + ox) / s, (yy + oy) / s   # sample in 4K design space
                acc += trace(px.ravel(), py.ravel(), ops, paper).reshape(y1 - y0, w, 3)
        img[y0:y1] = acc / (SS * SS)
    # paper texture: faint fibre noise
    rng = np.random.default_rng(0)
    img *= (1 + rng.normal(0, 0.012, (h, w, 1))).astype(np.float32)
    save_rgb(img, out_path("06-suminagashi", f"suminagashi--{name}", s))


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
