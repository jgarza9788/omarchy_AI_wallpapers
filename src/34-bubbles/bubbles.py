"""34 — Bubbles: every installed thing as a glossy marble, sized by bytes.

The real inventory (src/inventory.py) as a two-level circle packing: each item
is a sphere whose *area* is proportional to its installed size, packed tightly
inside its source (core, extra, flatpak runtimes, mise toolchains, plugins, ...),
and the source clusters are packed onto the screen. Spheres are shaded as glossy
marbles in their source's theme colour; the biggest ones carry their name, each
cluster gets a label with its count and total size.

Packing is greedy: largest first, each circle goes to the free spot nearest the
centre (measured elliptically for the clusters, so they fill 16:9) among spots
tangent to the circles already placed.

Usage: python3 src/34-bubbles/bubbles.py [--scheme omarchy|all] [--scale 0.25]
"""
import hashlib
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import inventory  # noqa: E402
from appfield import brand, write  # noqa: E402
from common import FONTS, H, W, hex2arr, out_path, scheme_args  # noqa: E402

SCHEMES = ["omarchy", "catppuccin", "tokyo-night", "everforest"]
FONT = str(FONTS / "SpaceMono" / "SpaceMonoNerdFontMono-Regular.ttf")
GAP = 1.5                                   # px between spheres (4K)


def pack(radii, aspect=1.0, gap=GAP):
    """Greedy packing (radii sorted desc): each circle goes to the free spot nearest the centre
    among candidates tangent to recently placed circles. Returns centres (N, 2) around the origin."""
    n = len(radii)
    pos = np.zeros((n, 2))
    ang = np.linspace(0, 2 * np.pi, 32, endpoint=False)
    unit = np.stack([np.cos(ang), np.sin(ang)], 1)
    for i in range(1, n):
        r = radii[i]
        src = np.unique(np.r_[np.arange(min(i, 12)), np.arange(max(0, i - 120), i)])
        cand = (pos[src, None, :] + (radii[src, None, None] + r + gap) * unit[None]).reshape(-1, 2)
        d = np.hypot(cand[:, None, 0] - pos[None, :i, 0], cand[:, None, 1] - pos[None, :i, 1])
        ok = np.all(d >= radii[None, :i] + r + gap - 1e-6, axis=1)
        if not ok.any():
            cand, ok = np.array([[0.0, (np.hypot(*pos[:i].T) + radii[:i]).max() + r + gap]]), np.array([True])
        score = np.hypot(cand[:, 0] / aspect, cand[:, 1])
        pos[i] = cand[ok][np.argmin(score[ok])]
    return pos


def shade_sphere(img, cx, cy, r, col, hi, s):
    """Draw a glossy sphere into img (float RGB) at output-pixel coords."""
    h, w, _ = img.shape
    x0, x1 = max(int(cx - r - 1), 0), min(int(cx + r + 2), w)
    y0, y1 = max(int(cy - r - 1), 0), min(int(cy + r + 2), h)
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dx, dy = (xx - cx) / r, (yy - cy) / r
    d2 = dx * dx + dy * dy
    cover = np.clip((1 - np.sqrt(d2)) * r + 0.5, 0, 1)                 # anti-aliased disc
    nz = np.sqrt(np.clip(1 - d2, 0, 1))
    lam = np.clip(-0.45 * dx - 0.55 * dy + 0.7 * nz, 0, 1)               # light from the upper left
    spec = np.clip(-0.4 * dx - 0.5 * dy + 0.77 * nz, 0, 1) ** 40
    rim = (1 - nz) ** 3
    c = col[None, None] * (0.25 + 0.8 * lam[..., None]) + hi * (0.85 * spec[..., None]) + col * 0.35 * rim[..., None]
    img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - cover[..., None]) + c * cover[..., None]


def short(it):
    """A compact label: flatpak ids lose their reverse-DNS prefix, versions keep two parts."""
    n = it["name"]
    if it["source"] in ("flatpak", "runtime"):
        parts = n.split(".")
        n = ".".join(parts[-2:]) if parts[-1] in ("default", "i386", "Intel", "Platform") else parts[-1]
    if "@" in n:
        tool, ver = n.split("@", 1)
        n = tool + " " + ".".join(ver.split(".")[:2])
    return n.removesuffix("-bin")


def render(name, pal, s):
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    cols = {k: hex2arr(v) for k, v in inventory.source_colors(pal).items()}
    hi = c.get("bright_foreground", c["foreground"])
    inv = inventory.load()
    total = sum(i["bytes"] for i in inv)

    # radii: area ∝ bytes, scaled so the spheres cover ~55% of the screen
    k = math.sqrt(0.55 * W * H / (math.pi * total))
    groups = []
    for src in inventory.SOURCES:
        items = sorted((i for i in inv if i["source"] == src), key=lambda i: -i["bytes"])
        if not items:
            continue
        r = np.array([max(k * math.sqrt(i["bytes"]), 2.5) for i in items])
        p = pack(r)
        R = float(np.max(np.hypot(*p.T) + r)) + 10
        groups.append((src, items, r, p, R))
    groups.sort(key=lambda g: -g[4])
    centres = pack(np.array([g[4] for g in groups]), aspect=1.7, gap=26)
    lo = (centres - np.array([g[4] for g in groups])[:, None]).min(0)
    hi_ = (centres + np.array([g[4] for g in groups])[:, None]).max(0)
    fit = min((W - 240) / (hi_[0] - lo[0]), (H - 300) / (hi_[1] - lo[1]))
    shift = np.array([W / 2, H / 2 - 40]) - (lo + hi_) / 2 * fit

    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    img = (c["background"] * (1 - yy) + c.get("darker_background", c["background"]) * yy) * np.ones((h, w, 3), np.float32)
    font_px = lambda px: str(max(int(px * s), 6))  # noqa: E731
    post = ["-font", FONT]
    for (src, items, r, p, R), gc in zip(groups, centres):
        col = cols[src]
        G = gc * fit + shift
        for rr, pp, it in zip(r, p, items):
            X, Y = (G + pp * fit) * s
            shade_sphere(img, X, Y, rr * fit * s, col * (0.75 + 0.25 * (it["explicit"])), hi, s)
            label = short(it)
            pt = min(rr * fit * 0.3, 1.7 * rr * fit / (0.6 * len(label)), 34)    # fit inside the sphere
            if pt >= 16:                                                    # names on the big ones
                post += ["-pointsize", font_px(pt), "-fill", pal["background"], "-gravity", "northwest",
                         "-annotate", f"+{int(X - len(label) * pt * 0.3 * s)}+{int(Y - pt * 0.62 * s)}", label]
        n, b = len(items), sum(i["bytes"] for i in items)
        lx, ly = (G + np.array([0, R * fit + 14])) * s
        text = f"{inventory.LABELS[src]}  {n} · {inventory.human(b)}"
        post += ["-pointsize", font_px(22), "-fill", pal.get("foreground"), "-undercolor", pal["background"] + "b0",
                 "-gravity", "northwest", "-annotate", f"+{int(lx - len(text) * 22 * 0.3 * s)}+{int(ly)}", text,
                 "+undercolor"]
    post += brand(pal, s, f"BUBBLES  ·  {len(inv)} ITEMS  ·  {inventory.human(total)}  ·  AREA ~ BYTES  ·  {name.upper()}")
    write(np.clip(img, 0, 1), out_path("34-bubbles", f"bubbles--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
