"""09 — Sigils: every theme's name grows its own strange attractor.

Following J.C. Sprott ("Strange Attractors: Creating Patterns in Chaos"), a 2D
quadratic map
    x' = a0 + a1·x + a2·x² + a3·x·y + a4·y + a5·y²
    y' = a6 + a7·x + a8·x² + a9·x·y + a10·y + a11·y²
is named by a 12-letter code, each letter A..Y meaning -1.2..+1.2 in 0.1 steps.
The theme name is hashed into a stream of candidate codes; the first one that is
genuinely chaotic (bounded, positive Lyapunov exponent, fills enough of the
plane) becomes that theme's sigil. So the shape is different for every theme,
not just the colours. ~60M orbit points are binned into a density histogram,
log tone-mapped and coloured by the local direction of motion.

Usage: python3 src/09-sigils/sigils.py [--scheme vantablack|all] [--scale 0.25]
"""
import hashlib
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import FONTS, H, W, box_blur, hex2arr, out_path, ramp, save_rgb, scheme_args  # noqa: E402

SCHEMES = ["vantablack", "lumon", "ristretto", "hackerman", "white"]
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXY"


def step(a, x, y):
    """Apply the quadratic map; a has shape (12, n) for n parallel candidates."""
    xn = a[0] + a[1] * x + a[2] * x * x + a[3] * x * y + a[4] * y + a[5] * y * y
    yn = a[6] + a[7] * x + a[8] * x * x + a[9] * x * y + a[10] * y + a[11] * y * y
    return xn, yn


def find_sigil(name, batch=20000):
    """Deterministically search hash-seeded codes for a chaotic attractor."""
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:16], 16)
    rng = np.random.default_rng(seed)
    while True:
        codes = rng.integers(0, 25, (12, batch))
        a = (codes - 12) / 10.0
        x, y = np.full(batch, 0.05), np.full(batch, 0.05)
        # shadow orbit for the Lyapunov exponent
        xe, ye = x + 1e-7, y.copy()
        lyap = np.zeros(batch)
        ok = np.ones(batch, bool)
        xs, ys = [], []
        with np.errstate(all="ignore"):
            for i in range(3000):
                x, y = step(a, x, y)
                xe, ye = step(a, xe, ye)
                ok &= np.isfinite(x) & np.isfinite(y) & (np.abs(x) < 1e6) & (np.abs(y) < 1e6)
                d = np.sqrt((xe - x) ** 2 + (ye - y) ** 2)
                if i > 500:
                    lyap += np.log(np.where(ok & (d > 0), d / 1e-7, 1))
                    if i % 10 == 0:
                        xs.append(x.copy())
                        ys.append(y.copy())
                # renormalise the shadow orbit
                f = np.where(d > 0, 1e-7 / d, 1)
                xe, ye = x + (xe - x) * f, y + (ye - y) * f
        lyap /= 2500
        X, Y = np.array(xs), np.array(ys)
        span_x = np.ptp(np.nan_to_num(X), axis=0)
        span_y = np.ptp(np.nan_to_num(Y), axis=0)
        good = ok & (lyap > 0.01) & (span_x > 0.05) & (span_y > 0.05)
        for j in np.nonzero(good)[0]:
            # coverage test: how many cells of a 40x40 grid the orbit touches
            gx = ((X[:, j] - X[:, j].min()) / (span_x[j] + 1e-12) * 39).astype(int)
            gy = ((Y[:, j] - Y[:, j].min()) / (span_y[j] + 1e-12) * 39).astype(int)
            cover = len(set(zip(gx.tolist(), gy.tolist()))) / 1600
            if 0.08 < cover < 0.38:
                return "".join(LETTERS[c] for c in codes[:, j]), a[:, j], lyap[j]


def render(name, pal, s):
    code, a, lyap = find_sigil(name)
    w, h = int(W * s), int(H * s)
    rng = np.random.default_rng(1)
    a = a[:, None]

    # warm up many parallel orbits onto the attractor
    n = 200_000
    x, y = rng.uniform(-0.1, 0.1, n), rng.uniform(-0.1, 0.1, n)
    with np.errstate(all="ignore"):
        for _ in range(200):
            x, y = step(a, x, y)
    keep = np.isfinite(x) & np.isfinite(y) & (np.abs(x) < 1e3) & (np.abs(y) < 1e3)
    x, y = x[keep], y[keep]
    # bounds from a longer sample of the orbit, not just the warm-up positions
    bx, by = [x], [y]
    with np.errstate(all="ignore"):
        tx, ty = x[:20000], y[:20000]
        for _ in range(100):
            tx, ty = step(a, tx, ty)
            bx.append(tx)
            by.append(ty)
    bx, by = np.concatenate(bx), np.concatenate(by)
    lo_x, hi_x = np.percentile(bx, [0.01, 99.99])
    lo_y, hi_y = np.percentile(by, [0.01, 99.99])

    # fit the attractor into a box of 82% of the screen height, centred
    box = 0.78 * h
    k = box / max(hi_x - lo_x, hi_y - lo_y)
    ox, oy = w / 2 - (lo_x + hi_x) / 2 * k, h / 2 - (lo_y + hi_y) / 2 * k

    dens = np.zeros(w * h)
    vcos = np.zeros(w * h)
    vsin = np.zeros(w * h)
    iters = int(300 * max(s, 0.25) ** 0.5)
    with np.errstate(all="ignore"):
        for _ in range(iters):
            xn, yn = step(a, x, y)
            px, py = (xn * k + ox).astype(np.int64), (yn * k + oy).astype(np.int64)
            inb = (px >= 0) & (px < w) & (py >= 0) & (py < h)
            idx = py[inb] * w + px[inb]
            ang = np.arctan2((yn - y)[inb], (xn - x)[inb])
            dens += np.bincount(idx, minlength=w * h)
            vcos += np.bincount(idx, weights=np.cos(ang), minlength=w * h)
            vsin += np.bincount(idx, weights=np.sin(ang), minlength=w * h)
            x, y = xn, yn
    dens = dens.reshape(h, w)
    hue = (np.arctan2(vsin, vcos).reshape(h, w) / (2 * np.pi)) % 1.0

    # tone mapping: log density, normalised on a high percentile
    lum = np.log1p(dens) / np.log1p(dens.max())
    lum = np.clip(lum * 1.1, 0, 1) ** 2.2
    light = pal["mode"] == "light"
    inks = [hex2arr(pal[k]) for k in ("accent", "magenta", "cyan", "yellow", "red", "blue")]
    inks.append(inks[0])  # make the hue ramp cyclic
    col = ramp(inks, hue)
    hi = hex2arr(pal.get("bright_foreground", pal["foreground"]))
    col = col * (1 - lum[..., None] ** 3 * 0.6) + hi * (lum[..., None] ** 3 * 0.6)  # hot cores go white
    glow = box_blur(lum, 6 * s * 4)[..., None]
    bg = hex2arr(pal["background"])
    if light:
        ink = np.clip(lum[..., None] ** 0.55 * 1.2, 0, 1)
        img = bg * (1 - ink) + col * 0.85 * ink
    else:
        img = bg + col * np.clip(lum[..., None] * 1.3 + glow * 0.35, 0, 1)

    font = str(FONTS / "SpaceMono" / "SpaceMonoNerdFontMono-Regular.ttf")
    pt = max(int(30 * s), 7)
    m = int(110 * s)
    dim = pal.get("dark_foreground", pal["foreground"])
    post = ["-font", font, "-fill", dim, "-pointsize", str(pt), "-kerning", str(int(pt * 0.35)),
            "-gravity", "southeast", "-annotate", f"+{m}+{m}", f"{name.upper()}  ⟶  {code}",
            "-pointsize", str(int(pt * 0.7)), "-annotate", f"+{m}+{m + int(pt * 1.6)}",
            f"lyapunov λ = {lyap:.3f}"]
    save_rgb(img, out_path("09-sigils", f"sigil--{name}", s), post)
    print(f"  {name}: {code}  lyapunov={lyap:.3f}")


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
