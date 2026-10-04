"""32 — Periodic Table of the Installed.

Everything installed *on purpose* (src/inventory.py: explicitly installed pacman
packages, flatpak apps, AppImages, Omarchy and Hyprland plugins, mise tools,
~/.local/bin commands) laid out as chemical elements. Sources fill contiguous
column blocks, like the s/p/d/f blocks of the real table. Each tile has:
  * an "atomic number": install order (pacman install date, then everything else)
  * a two-letter symbol, made unique the way element symbols are (first letter + a later one)
  * its "atomic mass": installed size
  * a fill whose strength grows with log(size), in the source's theme colour
A legend names the blocks; the ten heaviest elements get an accent outline.

Usage: python3 src/32-periodic/periodic.py [--scheme omarchy|all] [--scale 0.25]
"""
import collections
import math
import pathlib
import re
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import inventory  # noqa: E402
from appfield import brand, write  # noqa: E402
from common import FONTS, H, W, hex2arr, out_path, scheme_args  # noqa: E402

SCHEMES = ["omarchy", "nord", "kanagawa", "ethereal"]
FONT = str(FONTS / "SpaceMono" / "SpaceMonoNerdFontMono-Regular.ttf")
BOLD = str(FONTS / "Iosevka" / "IosevkaNerdFontMono-Bold.ttf")
ROWS = 10


def elements(inv):
    keep = [i for i in inv if i["explicit"] and i["source"] != "runtime"]
    mise = collections.defaultdict(int)                       # one element per mise tool, all versions summed
    out = []
    for i in keep:
        if i["source"] == "mise":
            mise[i["name"].split("@")[0]] += i["bytes"]
        else:
            out.append(dict(i))
    out += [{"name": t, "source": "mise", "bytes": b, "date": "", "explicit": True} for t, b in mise.items()]
    out.sort(key=lambda i: (i["date"] or "9999", i["name"]))
    for z, it in enumerate(out, 1):
        it["z"] = z
    return out


def symbols(names):
    used, out = set(), []
    for n in names:
        base = re.sub(r"^(org|io|com|net)\.[^.]+\.", "", n.split("@")[0]).replace("omarchy-", "o").replace("jgarza.", "")
        letters = re.sub(r"[^a-z0-9]", "", base.lower()) or "x"
        cands = [letters[0].upper() + ch for ch in letters[1:]] + [letters[0].upper() + ch for ch in "xyzqjkw"]
        sym = next((c for c in cands if c not in used), letters[0].upper())
        used.add(sym)
        out.append(sym)
    return out


def mass(b):
    for u, k in (("G", 1e9), ("M", 1e6), ("K", 1e3)):
        if b >= k:
            v = b / k
            return f"{v:.1f}{u}" if v < 100 else f"{v:.0f}{u}"
    return f"{b}B"


def render(name, pal, s):
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    srccol = inventory.source_colors(pal)
    inv = inventory.load()
    els = elements(inv)
    # column-major fill, source by source, so every source is a contiguous block
    order = sorted(els, key=lambda i: (inventory.SOURCES.index(i["source"]), i["z"]))
    syms = dict(zip((e["name"] for e in order), symbols([e["name"] for e in order])))
    ncols = math.ceil(len(order) / ROWS)
    mx, top, bot = 110, 300, 310
    tw, th = (W - 2 * mx) / ncols, (H - top - bot) / ROWS
    heavy = {e["name"] for e in sorted(order, key=lambda e: -e["bytes"])[:10]}
    lmax = math.log10(max(e["bytes"] for e in order))

    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    img = (c["background"] * (1 - yy) + c.get("darker_background", c["background"]) * yy) * np.ones((h, w, 3), np.float32)
    px = lambda v: str(max(int(v * s), 5))  # noqa: E731
    post = []
    for k, e in enumerate(order):
        col, row = divmod(k, ROWS)
        x0, y0 = mx + col * tw, top + row * th
        sc = hex2arr(srccol[e["source"]])
        f = 0.1 + 0.4 * max(math.log10(max(e["bytes"], 10)) - 3, 0) / (lmax - 3)
        a0, a1 = int((x0 + 4) * s), int((x0 + tw - 4) * s)
        b0, b1 = int((y0 + 4) * s), int((y0 + th - 4) * s)
        img[b0:b1, a0:a1] = c["background"] * (1 - f) + sc * f
        img[b0:b0 + max(int(6 * s), 1), a0:a1] = sc                       # block colour strip
        if e["name"] in heavy:
            bw = max(int(3 * s), 1)
            for sl in (np.s_[b0:b0 + bw, a0:a1], np.s_[b1 - bw:b1, a0:a1], np.s_[b0:b1, a0:a0 + bw], np.s_[b0:b1, a1 - bw:a1]):
                img[sl] = c["accent"]
        fg = pal["foreground"]
        label = e["name"].split(".")[-1] if e["source"] == "flatpak" else e["name"]
        post += ["-fill", fg, "-font", FONT, "-pointsize", px(17), "-annotate", f"+{a0 + int(9 * s)}+{b0 + int(12 * s)}", str(e["z"]),
                 "-annotate", f"+{a1 - int((len(mass(e['bytes'])) * 10 + 9) * s)}+{b0 + int(12 * s)}", mass(e["bytes"]),
                 "-font", BOLD, "-pointsize", px(62),
                 "-annotate", f"+{int((x0 + tw / 2 - len(syms[e['name']]) * 15.5) * s)}+{b0 + int(38 * s)}", syms[e["name"]],
                 "-font", FONT, "-pointsize", px(13),
                 "-annotate", f"+{int((x0 + tw / 2 - min(len(label), 17) * 3.9) * s)}+{b1 - int(30 * s)}", label[:17]]
    # title + legend
    post = ["-gravity", "northwest"] + post
    post += ["-fill", pal["foreground"], "-font", BOLD, "-pointsize", px(64), "-annotate", f"+{int(mx * s)}+{int(110 * s)}",
             "PERIODIC TABLE OF THE INSTALLED", "-font", FONT, "-pointsize", px(22),
             "-fill", pal.get("dark_foreground", pal["foreground"]),
             "-annotate", f"+{int(mx * s)}+{int(200 * s)}",
             f"{len(order)} elements · everything installed on purpose · atomic number = install order · mass = installed size"]
    lx = mx + 1900
    for k, src in enumerate(s_ for s_ in inventory.SOURCES if any(e["source"] == s_ for e in order)):
        cx, cy = lx + (k % 4) * 440, 112 + (k // 4) * 44
        n = sum(e["source"] == src for e in order)
        post += ["-fill", srccol[src], "-draw", f"rectangle {int(cx * s)},{int((cy + 6) * s)} {int((cx + 26) * s)},{int((cy + 32) * s)}",
                 "-fill", pal["foreground"], "-pointsize", px(22), "-annotate", f"+{int((cx + 40) * s)}+{int(cy * s)}",
                 f"{inventory.LABELS[src]} ({n})"]
    post += brand(pal, s, f"PERIODIC  ·  {len(order)} ELEMENTS  ·  {name.upper()}", corner="southwest")
    write(np.clip(img, 0, 1), out_path("32-periodic", f"periodic--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
