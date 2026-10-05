"""47 — Disturbed Code: a screen of source code hit by a physical event.

A full page of syntax-highlighted code (this repo's own Python, coloured by token type
with the theme's ANSI colours, set in Iosevka) treated as a physical surface or medium.
Each scheme gets its own event:

* ripple — a droplet lands on the page as if it were water: capillary rings bend the
  text through the surface slope (refraction ∝ ∇h), with chromatic fringes and glints
* lens   — a black hole drifts across: the point-lens equation β = θ − θE²·θ/|θ|²
  wraps the lines into arcs and an Einstein ring of code around a black shadow
* wind   — a gust peels the characters off the right-hand ends of the lines and carries
  them away on a turbulent curl-noise stream
* melt   — heat from below: the glyphs warm through the palette, sag and drip downward

The code is only texture; the Omarchy wordmark signs the bottom-left corner.

Usage: python3 src/47-disturbed-code/disturbed_code.py [--scheme omarchy|all] [--scale 0.25]
"""
import hashlib
import io
import keyword
import math
import pathlib
import sys
import tokenize

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from appfield import Atlas, affine, blur3, brand, splat  # noqa: E402
from common import H, ROOT, W, box_blur, hex2arr, out_path, ramp, save_rgb, scheme_args, value_noise  # noqa: E402

EVENTS = {"omarchy": "ripple", "tokyo-night": "lens", "catppuccin": "wind", "gruvbox": "melt"}
SCHEMES = list(EVENTS)
PX = 26                                   # glyph pixel size at 4K; Iosevka advances 0.5 em
ADV, LEAD = PX * 0.5, PX * 1.3


def source_lines(rng):
    files = sorted((ROOT / "src").glob("*/*.py")) + sorted((ROOT / "src").glob("*.py"))
    rng.shuffle(files)
    out = []
    for f in files:
        text = f.read_text()
        out += [(text, f)]
    return out


TOKCACHE = {}


def tokens(text):
    """(line, col, string, kind) for every token, kind in kw/str/com/num/name/def/op."""
    if text in TOKCACHE:
        return TOKCACHE[text]
    res, prev = [], None
    try:
        for t in tokenize.generate_tokens(io.StringIO(text).readline):
            kind = None
            if t.type == tokenize.NAME:
                kind = "kw" if keyword.iskeyword(t.string) else ("def" if prev in ("def", "class") else "name")
            elif t.type == tokenize.STRING or tokenize.tok_name[t.type].startswith("FSTRING"):
                kind = "str"
            elif t.type == tokenize.COMMENT:
                kind = "com"
            elif t.type == tokenize.NUMBER:
                kind = "num"
            elif t.type == tokenize.OP:
                kind = "op"
            if kind:
                res.append((t.start[0], t.start[1], t.string, kind))
            if t.type == tokenize.NAME:
                prev = t.string
    except (tokenize.TokenError, IndentationError):
        pass
    TOKCACHE[text] = res
    return res


def page_chars(pal, rng, s, w, h):
    """Lay out code in columns filling the screen; returns arrays x, y, codepoint, rgb."""
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    col_of = {"kw": c["magenta"], "str": c["green"], "com": c.get("dark_foreground", c["foreground"]) * 0.8,
              "num": c.get("orange", c["yellow"]), "name": c["foreground"], "def": c["blue"], "op": c["cyan"]}
    adv, lead = ADV * s, LEAD * s
    ncols = 2
    width = int((w - 160 * s) / ncols / adv) - 4
    nrows = int((h - 90 * s) / lead)
    xs, ys, cps, cols = [], [], [], []
    files = source_lines(rng)
    fi, line0 = 0, 0
    for col in range(ncols):
        x0 = 80 * s + col * (w - 160 * s) / ncols
        row = 0
        while row < nrows:
            text, _ = files[fi % len(files)]
            fi += 1
            lines = text.splitlines()
            start = int(rng.integers(0, max(len(lines) - 20, 1)))
            seg = lines[start:start + nrows - row]
            for (ln, cc, st, kind) in tokens(text):
                ln -= start
                if not 1 <= ln <= len(seg):
                    continue
                for k, ch in enumerate(st.split("\n")[0]):
                    if ch == " " or cc + k >= width:
                        continue
                    xs.append(x0 + (cc + k + 0.5) * adv)
                    ys.append(45 * s + (row + ln - 1 + 0.5) * lead)
                    cps.append(ord(ch))
                    cols.append(col_of[kind])
            row += len(seg) + 1
    del line0
    return np.array(xs), np.array(ys), np.array(cps), np.array(cols)


def draw(w, h, xs, ys, cps, cols, atlas, px, alpha=None, A=None):
    rgb = np.zeros((h, w, 3), np.float32)
    a = np.zeros((h, w), np.float32)
    for i in range(len(xs)):
        m = atlas.get(int(cps[i]), px)
        if A is not None and A[i] is not None:
            from appfield import warp
            m = warp(m, A[i])
        mh, mw = m.shape
        x0, y0 = int(round(xs[i] - mw / 2)), int(round(ys[i] - mh / 2))
        xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + mw, w), min(y0 + mh, h)
        if xa >= xb or ya >= yb:
            continue
        mm = m[ya - y0:yb - y0, xa - x0:xb - x0] * (1 if alpha is None else alpha[i])
        rgb[ya:yb, xa:xb] += cols[i] * mm[..., None]
        a[ya:yb, xa:xb] = np.maximum(a[ya:yb, xa:xb], mm)
    return rgb, a


def sample(img, sx, sy):
    """Bilinear lookup of img (h, w[, 3]) at float coords, clamped at the edges."""
    h, w = img.shape[:2]
    sx = np.clip(sx, 0, w - 1.001)
    sy = np.clip(sy, 0, h - 1.001)
    x0, y0 = sx.astype(int), sy.astype(int)
    fx, fy = sx - x0, sy - y0
    if img.ndim == 3:
        fx, fy = fx[..., None], fy[..., None]
    return ((img[y0, x0] * (1 - fx) + img[y0, x0 + 1] * fx) * (1 - fy)
            + (img[y0 + 1, x0] * (1 - fx) + img[y0 + 1, x0 + 1] * fx) * fy)


def render(name, pal, s):
    event = EVENTS[name]
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    bg = c["background"]
    atlas = Atlas()
    px = max(int(PX * s), 5)
    xs, ys, cps, cols = page_chars(pal, rng, s, w, h)
    sig = (xs < 700 * s) & (ys > h - 290 * s)                 # leave room for the wordmark signature
    xs, ys, cps, cols = xs[~sig], ys[~sig], cps[~sig], cols[~sig]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    glow = np.zeros((h, w, 3), np.float32)

    if event == "wind":
        # characters past a ragged front detach and ride a curl-noise stream to the right and up
        front = w * (0.42 + 0.22 * value_noise(1, 64, 8, rng, octaves=3)[0])
        fx = np.interp(ys, np.linspace(0, h, 64), front)
        p_det = np.clip((xs - fx) / (w * 0.25), 0, 1) ** 0.8
        det = rng.random(len(xs)) < p_det
        gh, gw = 54, 96
        psi = value_noise(gh, gw, 12, rng, octaves=4) * 2 - 1
        vx_f = np.gradient(psi, axis=0) * 90 + 0.8
        vy_f = -np.gradient(psi, axis=1) * 90 - 0.35
        n = det.sum()
        pxy = np.stack([xs[det], ys[det]], 1)
        steps = 70
        dt = (0.15 + 0.85 * rng.random(n)) * (np.clip((xs[det] - fx[det]) / (w * 0.3), 0, 1) + 0.15) * 22 * s
        trail = []
        for k in range(steps):
            gx, gy = pxy[:, 0] / w * (gw - 1), pxy[:, 1] / h * (gh - 1)
            vx = sample(vx_f, gx, gy)
            vy = sample(vy_f, gx, gy)
            pxy = pxy + np.stack([vx, vy], 1) * dt[:, None]
            trail.append(pxy.copy())
        trail = np.array(trail)
        for k in range(0, steps, 2):
            fade = (k / steps) ** 1.5 * 0.16
            splat(glow, trail[k, :, 0], trail[k, :, 1], cols[det], np.full(n, fade, np.float32))
        spin = [affine(angle=float(a), stretch=1.2, squash=0.85) for a in rng.normal(0, 1.4, n)]
        xs2, ys2 = xs.copy(), ys.copy()
        xs2[det], ys2[det] = trail[-1, :, 0], trail[-1, :, 1]
        Aall = [None] * len(xs)
        for j, i in enumerate(np.nonzero(det)[0]):
            Aall[i] = spin[j]
        alpha = np.where(det, 0.9, 1.0)
        rgb, a = draw(w, h, xs2, ys2, cps, cols, atlas, px, alpha, Aall)
        img = bg * (1 - a[..., None]) + rgb
        img = img + (1 - np.exp(-glow * 2.5)) * (1 - img) * 0.9
    else:
        rgb, a = draw(w, h, xs, ys, cps, cols, atlas, px)
        page = bg * (1 - a[..., None]) + rgb
        if event == "ripple":
            cx, cy = w * rng.uniform(0.55, 0.68), h * rng.uniform(0.4, 0.55)
            hgt = np.zeros((h, w), np.float32)
            for (ox, oy, amp, rf) in ((cx, cy, 1.0, 0.36), (cx - w * 0.33, cy + h * 0.2, 0.45, 0.17)):
                r = np.hypot(xx - ox, yy - oy) / h
                lam = 0.035 + 0.02 * r                                   # capillary waves: longer outward
                env = np.exp(-((r - rf) / (rf * 0.5)) ** 2) + 0.25 * np.exp(-r / (rf * 0.2))
                hgt += amp * np.sin(2 * np.pi * r / lam) * env
            gy_, gx_ = np.gradient(hgt)
            D, S = 380 * s * s, 4 * s
            img = np.stack([sample(page[..., ch], xx - gx_ * D * (1 + 0.1 * ch), yy - gy_ * D * (1 + 0.1 * ch))
                            for ch in range(3)], -1)
            nrm = np.stack([-gx_ * S, -gy_ * S, np.ones_like(gx_)], -1)
            nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
            L = np.array([-0.5, -0.6, 0.62])
            spec = np.clip((nrm @ (L / np.linalg.norm(L))) - 0.9, 0, 1) ** 2 * 40
            img = img + spec[..., None] * (c.get("bright_foreground", c["foreground"]) - img) * 0.8
            img = img * (1 - 0.3 * np.clip(-hgt, 0, 1)[..., None]) + c["accent"] * 0.05 * np.clip(hgt, 0, 1)[..., None]
        elif event == "lens":
            cx, cy = w * rng.uniform(0.56, 0.66), h * rng.uniform(0.42, 0.52)
            tE = h * 0.2
            dx, dy = xx - cx, yy - cy
            r2 = dx * dx + dy * dy + 1e-3
            bx, by = cx + dx - tE * tE * dx / r2, cy + dy - tE * tE * dy / r2
            img = sample(page, bx, by)
            r = np.sqrt(r2)
            shadow = 1 - np.clip((r - tE * 0.62) / (tE * 0.04), 0, 1)
            ring = np.exp(-((r - tE * 0.66) / (tE * 0.03)) ** 2)
            img = img * (1 - shadow[..., None]) + c["darker_background"] * shadow[..., None] * 0.2
            img = img + ring[..., None] * (c.get("orange", c["yellow"]) * 0.6 + c["accent"] * 0.4) * 0.9
            glow += ring[..., None] * c.get("orange", c["yellow"]) * 0.8
        elif event == "melt":
            y0 = h * 0.28
            heat = np.clip((yy - y0) / (h - y0), 0, 1)
            drip = value_noise(1, w, int(40 * s) + 2, rng, octaves=3)[0]
            drip = (np.clip(drip - 0.35, 0, 1) / 0.65) ** 3
            D = h * (0.03 + 0.5 * drip[None, :]) * heat ** 2.4
            sx = xx + 3 * s * np.sin(yy / (37 * s) + xx / (91 * s)) * heat
            img = sample(page, sx, yy - D)
            al = sample(a, sx, yy - D)
            warm = ramp([c["red"], c.get("orange", c["yellow"]), c["yellow"]], heat * 0.9 + drip[None, :] * 0.1)
            t = (heat ** 0.8)[..., None] * al[..., None]
            img = img * (1 - t) + (warm * 0.85 + img * 0.15) * t
            glow += c.get("orange", c["red"]) * (heat ** 2.5)[..., None] * 0.35
            glow += c["red"] * np.exp(-((h - yy) / (h * 0.08)))[..., None] * 1.2
        img = img + (1 - np.exp(-blur3(glow, 30 * s) * 2.0)) * (1 - img) * 0.7

    # keep the signature corner calm after the warp too
    calm = np.clip((760 * s - xx) / (80 * s), 0, 1) * np.clip((yy - (h - 330 * s)) / (60 * s), 0, 1)
    img = img * (1 - calm[..., None]) + blur3(img, 140 * s) * calm[..., None]

    # soft vignette
    v = 1 - 0.35 * np.clip(((xx / w - 0.5) ** 2) * 1.4 + ((yy / h - 0.5) ** 2) * 1.6, 0, 1)
    img = img * v[..., None]
    img = img + blur3(np.clip(img - 0.55, 0, 1), 10 * s) * 0.4
    save_rgb(img, out_path("47-disturbed-code", f"code-{event}--{name}", s),
             brand(pal, s, f"{event.upper()}  ·  {name.upper()}"))


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
