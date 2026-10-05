"""40 — Sampler: a Victorian cross-stitch sampler of the GitHub year.

Worked on aida cloth, as samplers were: a vine border with corner flowers, an
alphabet row and numerals, the motto THERE'S NO PLACE LIKE ~, and a little
scene. The scene is the data (src/github_stats.py): the last 53 weeks of
contributions are the garden bed in front of the house (one 2×2 block a day,
from leaf green to full bloom), one tree per 20 repositories stands in the
orchard, and the fence is as long as the longest streak, a post per ten days.
It is signed the traditional way, WROUGHT BY <login> IN <year>.

Every stitch is a real X: two thread legs, the top one always crossing the
same way, each shaded round with a twist, sunk into the holes of the weave.
The needle is left on the cloth with its thread running back to the last stitch.

Usage: python3 src/40-sampler/sampler.py [--scheme omarchy|all] [--scale 0.5]
"""
import datetime as dt
import pathlib
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import github_stats  # noqa: E402
from appfield import brand, write  # noqa: E402
from common import FONTS, H, ROOT, W, box_blur, hex2arr, out_path, scheme_args, value_noise  # noqa: E402

SCHEMES = ["omarchy", "rose-pine", "gruvbox", "catppuccin-latte"]
CELL = 16                                   # stitch pitch in full-size pixels
GW, GH = W // CELL, H // CELL               # 240 × 135 stitches
PIXFONT = str(FONTS / "3270" / "3270NerdFontMono-Regular.ttf")


def bitmap(text, pt=12):
    """Text as a boolean stitch grid, from the 3270 pixel font rendered without antialiasing."""
    raw = subprocess.run(["magick", "-background", "black", "-fill", "white", "-font", PIXFONT, "-pointsize", str(pt),
                          "+antialias", f"label:{text}", "-trim", "+repage", "-depth", "8", "gray:-"],
                         capture_output=True, check=True).stdout
    size = subprocess.run(["magick", "-background", "black", "-fill", "white", "-font", PIXFONT, "-pointsize", str(pt),
                           "+antialias", f"label:{text}", "-trim", "+repage", "-format", "%w %h", "info:"],
                          capture_output=True, text=True, check=True).stdout.split()
    w, h = int(size[0]), int(size[1])
    return np.frombuffer(raw, np.uint8).reshape(h, w) > 127


class Pattern:
    def __init__(self):
        self.p = np.zeros((GH, GW), np.int16)            # 0 = bare cloth, otherwise a thread index
        self.last = (0, 0)

    def put(self, r, c, k):
        if 0 <= r < GH and 0 <= c < GW:
            self.p[r, c] = k
            self.last = (r, c)

    def blit(self, mask, r0, c0, k, scale=1):
        for r, c in zip(*np.nonzero(mask)):
            for dr in range(scale):
                for dc in range(scale):
                    self.put(r0 + r * scale + dr, c0 + c * scale + dc, k)

    def text(self, s, r0, k, pt=12, center=True, c0=0):
        m = bitmap(s, pt)
        self.blit(m, r0, (GW - m.shape[1]) // 2 if center else c0, k)
        return m.shape


# thread palette: index -> palette key (resolved per scheme)
THREADS = {1: "foreground", 2: "accent", 3: "green", 4: "red", 5: "yellow", 6: "blue", 7: "magenta", 8: "cyan",
           9: "brown", 10: "dark_foreground", 11: "bright_green", 12: "orange"}


def design(gh):
    P = Pattern()
    # border: a wavy vine with leaves, flowers at the corners
    inset = 5
    edge = []
    for c in range(inset, GW - inset):
        edge.append((inset, c))
    for r in range(inset, GH - inset):
        edge.append((r, GW - inset - 1))
    for c in range(GW - inset - 1, inset - 1, -1):
        edge.append((GH - inset - 1, c))
    for r in range(GH - inset - 1, inset - 1, -1):
        edge.append((r, inset))
    for i, (r, c) in enumerate(edge):
        wob = int(round(1.2 * np.sin(i / 4.0)))
        inward = (1 if r == inset else -1 if r == GH - inset - 1 else 0, 1 if c == inset else -1 if c == GW - inset - 1 else 0)
        rr, cc = r + wob * inward[0], c + wob * inward[1]
        P.put(rr, cc, 3)
        if i % 7 == 3:                                       # a leaf off the stem, alternating sides
            sgn = 1 if (i // 7) % 2 else -1
            for d in (1, 2):
                P.put(rr + sgn * d * (inward[0] or 1) * (1 if inward[0] else 0) + (d if not inward[0] else 0) * 0,
                      cc + sgn * d * (inward[1] or 0) + (d if inward[0] else 0) * sgn, 11)
    for r0, c0 in ((inset, inset), (inset, GW - inset - 1), (GH - inset - 1, inset), (GH - inset - 1, GW - inset - 1)):
        for dr, dc in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1), (-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            P.put(r0 + dr, c0 + dc, 4 if abs(dr) + abs(dc) == 2 and dr and dc else 7)
        P.put(r0, c0, 5)
    # alphabet, numerals, motto
    P.text("ABCDEFGHIJKLMNOPQRSTUVWXYZ", 13, 6)
    P.text("0123456789  & ~ $ #", 25, 12)
    P.text("THERE'S NO PLACE LIKE ~", 39, 2, pt=13)
    for c in range(30, GW - 30, 3):                          # a row of little diamonds under the motto
        P.put(52, c, 7 if (c // 3) % 2 else 8)
    # the scene: sun, birds, house, garden, orchard, fence
    for r in range(-4, 5):
        for c in range(-4, 5):
            if r * r + c * c <= 16:
                P.put(66 + r, 26 + c, 5)
    for i in range(8):
        P.put(66 + int(7 * np.sin(i * np.pi / 4)), 26 + int(7 * np.cos(i * np.pi / 4)), 5)
    for r0, c0 in ((60, 70), (63, 82), (58, 120)):
        for d, (dr, dc) in enumerate(((0, 0), (-1, 1), (0, 2), (-1, 3), (0, 4))):
            P.put(r0 + dr, c0 + dc, 10)
    hr, hc = 70, 18                                           # house: roof, chimney, walls, windows, door
    for r in range(10):
        for c in range(12 - r - 2, 12 + r + 3):
            P.put(hr + r, hc + c, 9 if (r + c) % 4 else 7)
    for r in range(-4, 2):
        P.put(hr + r, hc + 18, 9)
        P.put(hr + r, hc + 19, 9)
    for r in range(10, 30):
        for c in range(1, 24):
            P.put(hr + r, hc + c, 4)
    for wr, wc in ((13, 4), (13, 15)):
        for r in range(5):
            for c in range(5):
                P.put(hr + wr + r, hc + wc + c, 5 if r != 2 and c != 2 else 1)
    for r in range(21, 30):
        for c in range(9, 15):
            P.put(hr + r, hc + c, 6)
    P.put(hr + 25, hc + 13, 5)
    g0c, g0r = 50, 86                                         # the garden bed: the contribution calendar
    if gh:
        days = gh["calendar"][-53 * 7:]
        hi = sorted(n for n in days if n)
        qs = [hi[int(len(hi) * q)] for q in (0.25, 0.5, 0.75)] if hi else [1, 2, 3]
        bloom = {1: 3, 2: 11, 3: 7, 4: 5}
        for i, n in enumerate(days):
            if not n:
                continue
            lvl = 1 + sum(n > q for q in qs)
            r, c = g0r + (i % 7) * 2, g0c + (i // 7) * 2
            for dr in (0, 1):
                for dc in (0, 1):
                    P.put(r + dr, c + dc, bloom[lvl])
        n_trees = max(1, round(gh["repos"] / 20))
        posts = max(2, gh["longest_streak"] // 10)
    else:
        n_trees, posts = 6, 10
    for c in range(g0c - 1, g0c + 107):                       # soil line under the bed
        P.put(g0r + 15, c, 9)
    for t in range(n_trees):                                  # orchard: rows of round trees
        tr, tc = 66 + (t % 2) * 16, 166 + (t // 2) * 11 + (t % 2) * 5
        for r in range(-4, 5):
            for c in range(-4, 5):
                if r * r + c * c <= 15:
                    P.put(tr + r, tc + c, 3 if (r + c) % 5 else 11)
        P.put(tr + 1, tc - 1, 4)
        P.put(tr - 2, tc + 2, 4)
        for r in range(5, 9):
            P.put(tr + r, tc, 9)
    fr = g0r + 18                                             # fence: a post per ten days of the longest streak
    for k in range(posts):
        c = g0c - 2 + k * 4
        if c > GW - 12:
            break
        for r in range(5):
            P.put(fr + r, c, 1)
        P.put(fr - 1, c, 10)
        for r in (fr + 1, fr + 3):
            for dc in range(1, 4):
                if k < posts - 1:
                    P.put(r, c + dc, 1)
    login = gh["login"].upper() if gh else "THIS MACHINE"
    P.text(f"WROUGHT BY {login} IN {dt.date.today().year}", 111, 1)
    return P


def stitch_sprites(c):
    """Shading and coverage for the two legs of one cross stitch, in a c×c cell."""
    y, x = np.mgrid[0:c, 0:c].astype(np.float32) + 0.5
    out = []
    for leg in (0, 1):                                        # 0: "\" under, 1: "/" over
        u = (x - y) / np.sqrt(2) if leg == 0 else (x + y - c) / np.sqrt(2)   # across the leg
        v = (x + y) / np.sqrt(2) if leg == 0 else (x - y + c) / np.sqrt(2)   # along the leg
        half = c * 0.21
        cover = np.clip((half - np.abs(u)) / 0.8, 0, 1)
        roundness = np.sqrt(np.clip(1 - (u / half) ** 2, 0, 1))
        twist = 0.85 + 0.15 * np.sin((v * 2.3 + u * 2.0) / c * 2 * np.pi * 3)
        ends = np.clip(np.minimum(v, c * np.sqrt(2) - v) / (c * 0.18), 0.35, 1)   # sinks into the holes
        shade = (0.45 + 0.75 * roundness) * twist * ends
        spec = np.exp(-((u + half * 0.35) / (half * 0.25)) ** 2) * 0.35 * ends
        out.append((cover, shade, spec))
    return out


def render(name, pal, s):
    gh = github_stats.load()
    P = design(gh)
    c = max(int(round(CELL * s)), 4)
    gw, gh_px = GW * c, GH * c
    rng = np.random.default_rng(40)
    light = pal.get("mode") == "light"
    get = lambda k: hex2arr(pal[k] if isinstance(pal.get(k), str) else pal["foreground"])  # noqa: E731
    cloth = (get("background") * 0.6 + np.array([0.93, 0.9, 0.84]) * 0.4) if light else get("background") * 0.8
    # aida weave: blocks of thread with holes at the corners of every cell
    y, x = np.mgrid[0:gh_px, 0:gw].astype(np.float32)
    fx, fy = (x % c) / c, (y % c) / c
    hole = np.exp(-((np.minimum(fx, 1 - fx) ** 2 + np.minimum(fy, 1 - fy) ** 2) / 0.012))
    weave = 0.9 + 0.08 * np.sin(fx * np.pi * 4) * np.sin(fy * np.pi * 4)
    grain = value_noise(gh_px, gw, max(c // 2, 2), rng, octaves=3)
    img = cloth * (weave * (0.94 + 0.12 * grain) * (1 - 0.55 * hole))[..., None]
    # threads
    idx = np.repeat(np.repeat(P.p, c, 0), c, 1)
    cols = np.zeros((len(THREADS) + 1, 3), np.float32)
    for k, key in THREADS.items():
        cols[k] = get(key)
    jitter = np.repeat(np.repeat(rng.uniform(0.92, 1.06, P.p.shape).astype(np.float32), c, 0), c, 1)
    thread = cols[idx] * jitter[..., None]
    on = (idx > 0).astype(np.float32)
    legs = stitch_sprites(c)
    reps = (GH, GW)
    shadow = np.zeros((gh_px, gw), np.float32)
    for cover, _, _ in legs:
        shadow = np.maximum(shadow, np.tile(cover, reps) * on)
    sh = box_blur(np.roll(np.roll(shadow, max(c // 8, 1), 0), max(c // 8, 1), 1), max(c // 6, 1))
    img *= (1 - 0.45 * sh)[..., None]
    for cover, shade, spec in legs:
        a = np.tile(cover, reps) * on
        sd = np.tile(shade, reps)
        sp = np.tile(spec, reps)
        lit = thread * sd[..., None] + sp[..., None]
        img = img * (1 - a[..., None]) + lit * a[..., None]
    # pad to the canvas (W*s × H*s)
    w, h = int(W * s), int(H * s)
    canvas = np.zeros((h, w, 3), np.float32) + cloth * 0.9
    canvas[:min(h, gh_px), :min(w, gw)] = img[:h, :w]
    vig = 1 - 0.25 * (((np.mgrid[0:h, 0:w][1] / w - 0.5) * 1.5) ** 2 + ((np.mgrid[0:h, 0:w][0] / h - 0.5) * 1.6) ** 2)
    canvas *= vig[..., None]

    # the needle and its thread, left on the cloth
    lr, lc = P.last
    tx, ty = (lc + 0.5) * CELL, (lr + 0.5) * CELL
    nx0, ny0, nx1, ny1 = 2420, 2010, 2900, 1930
    thread_hex = pal["foreground"]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
           '<defs><linearGradient id="steel" x1="0" y1="0" x2="0" y2="1">'
           '<stop offset="0" stop-color="#f4f6f8"/><stop offset="0.45" stop-color="#9aa3ad"/>'
           '<stop offset="1" stop-color="#4b525a"/></linearGradient>'
           '<filter id="sh"><feGaussianBlur stdDeviation="5"/></filter></defs>'
           f'<path d="M {tx:.0f},{ty:.0f} C {tx + 200:.0f},{ty + 160:.0f} {nx0 - 300},{ny0 + 120} {nx0 + 10},{ny0}" '
           f'fill="none" stroke="#000" stroke-opacity="0.35" stroke-width="9" filter="url(#sh)" transform="translate(6,8)"/>'
           f'<path d="M {tx:.0f},{ty:.0f} C {tx + 200:.0f},{ty + 160:.0f} {nx0 - 300},{ny0 + 120} {nx0 + 10},{ny0}" '
           f'fill="none" stroke="{thread_hex}" stroke-width="7" stroke-linecap="round"/>'
           f'<g transform="rotate(-9.5 {nx0} {ny0})">'
           f'<rect x="{nx0}" y="{ny0 + 10}" width="480" height="13" rx="6" fill="#000" fill-opacity="0.4" filter="url(#sh)"/>'
           f'<path d="M {nx0},{ny0 - 6} L {nx0 + 470},{ny0 - 1} L {nx0 + 486},{ny0} L {nx0 + 470},{ny0 + 1} '
           f'L {nx0},{ny0 + 6} Q {nx0 - 8},{ny0} {nx0},{ny0 - 6} Z" fill="url(#steel)"/>'
           f'<rect x="{nx0 + 10}" y="{ny0 - 2.2}" width="34" height="4.4" rx="2" fill="#2a2a2a"/></g></svg>')
    tmp = ROOT / ".wip" / f"sampler--{name}.svg"
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_text(svg)
    png = tmp.with_suffix(f".{s}.png")
    subprocess.run(["rsvg-convert", "-w", str(w), "-h", str(h), "-o", str(png), str(tmp)], check=True)
    post = [str(png), "-composite"] + brand(pal, s, f"SAMPLER  ·  {name.upper()}", corner="southeast")
    write(np.clip(canvas, 0, 1), out_path("40-sampler", f"sampler--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
