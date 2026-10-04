"""35 — Receipt: everything installed on this machine, itemised on thermal paper.

The real inventory (src/inventory.py: pacman repos, AUR, flatpak, AppImages,
Omarchy and Hyprland plugins, mise toolchains, ~/.local/bin) printed as a
till receipt: the heaviest line items with their sizes, a subtotal per source,
the grand total, dependencies billed as "tax", and a barcode whose bars are
the heaviest items (bar width ∝ log size, grouped by source). The receipt lies
tilted on a dark desk with a soft shadow and a rubber stamp in the accent colour.

Usage: python3 src/35-receipt/receipt.py [--scheme omarchy|all] [--scale 0.25]
"""
import datetime as dt
import hashlib
import math
import pathlib
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import inventory  # noqa: E402
from appfield import brand, write  # noqa: E402
from common import FONTS, H, ROOT, W, hex2arr, out_path, scheme_args, value_noise  # noqa: E402

SCHEMES = ["omarchy", "gruvbox", "rose-pine", "matte-black"]
FONT = str(FONTS / "3270" / "3270NerdFontMono-Regular.ttf")
COLS = 44
N_ITEMS = 12
BARS = 110


def lines(inv):
    hu = inventory.human
    pac = [i for i in inv if i["source"] in ("core", "extra", "omarchy", "aur")]
    out = [("c", "** OMARCHY SYSTEM SUPPLY CO. **"), ("c", "pacman · AUR · flatpak · mise · plugins"),
           ("c", dt.date.today().strftime("%Y-%m-%d") + "   TERMINAL 01   x86_64"), ("hr", ""),
           ("row", ("QTY ITEM", "SIZE")), ("hr", "")]
    grouped = {}                                                   # same name twice (flatpak branches) -> QTY 2
    for it in inv:
        q, b = grouped.get(it["name"], (0, 0))
        grouped[it["name"]] = (q + 1, b + it["bytes"])
    for nm, (q, b) in sorted(grouped.items(), key=lambda kv: -kv[1][1])[:N_ITEMS]:
        out.append(("row", (f"{q:>2}  {nm[:28]}", hu(b))))
    out += [("c", f"... {len(inv) - N_ITEMS} more items ..."), ("hr", ""), ("l", "SUBTOTALS")]
    for s, (n, b) in inventory.summary(inv).items():
        out.append(("row", (f" {inventory.LABELS[s]:<17}{n:>5}", hu(b))))
    out += [("hr", ""), ("big", ("ITEMS", f"{len(inv)}")), ("big", ("TOTAL", hu(sum(i['bytes'] for i in inv)))),
            ("row", ("TAX (dependencies)", f"{sum(not i['explicit'] for i in pac)} pkgs")), ("hr", ""),
            ("c", f"explicit {sum(i['explicit'] for i in pac)} · deps {sum(not i['explicit'] for i in pac)}"
                  f" · foreign {sum(i['source'] == 'aur' for i in pac)}"),
            ("bar", ""), ("c", "THANK YOU FOR USING ARCH (BTW)"), ("c", "no refunds on removed packages")]
    return out


def receipt_png(inv, pal, s, path):
    """Draw the receipt with ImageMagick: paper, text, barcode. Returns the PNG path."""
    pt = 30 * s
    lh = int(40 * s)
    cw = pt * 0.5
    pad = int(60 * s)
    rows = lines(inv)
    bar_h = int(170 * s)
    wpx = int(COLS * cw + 2 * pad)
    hpx = pad * 2 + lh * len(rows) + bar_h + lh * 2
    paper = "#f3efe6"
    ink = "#26241f"
    cmd = ["magick", "-size", f"{wpx}x{hpx}", f"xc:{paper}", "-font", FONT, "-fill", ink]
    y = pad
    for kind, val in rows:
        if kind == "hr":
            cmd += ["-pointsize", str(pt), "-gravity", "northwest", "-annotate", f"+{pad}+{y}", "-" * COLS]
        elif kind == "c":
            cmd += ["-pointsize", str(pt), "-gravity", "north", "-annotate", f"+0+{y}", val]
        elif kind == "l":
            cmd += ["-pointsize", str(pt), "-gravity", "northwest", "-annotate", f"+{pad}+{y}", val]
        elif kind in ("row", "big"):
            p = pt * (1.35 if kind == "big" else 1)
            right = wpx - pad - len(val[1]) * p * 0.5                # monospace: right-align by width
            cmd += ["-pointsize", str(p), "-gravity", "northwest", "-annotate", f"+{pad}+{y}", val[0],
                    "-annotate", f"+{right:.0f}+{y}", val[1]]
            if kind == "big":
                y += int(lh * 0.35)
        elif kind == "bar":                                     # every item is one bar, grouped by source
            big = sorted(inv, key=lambda i: -i["bytes"])[:BARS]            # the heaviest items, one bar each
            items = sorted(big, key=lambda i: (inventory.SOURCES.index(i["source"]), -i["bytes"]))
            widths = np.array([math.log10(max(i["bytes"], 10)) for i in items])
            widths = widths / widths.sum() * (wpx - 2 * pad)
            x, draw = float(pad), []
            for k, wd in enumerate(widths):
                if k % 2 == 0:
                    draw.append(f"rectangle {x:.1f},{y} {x + wd * 0.8:.1f},{y + bar_h}")
                x += wd
            cmd += ["-draw", " ".join(draw)]
            y += bar_h
            cmd += ["-pointsize", str(pt * 0.8), "-gravity", "north", "-annotate", f"+0+{y + int(6 * s)}",
                    "  ".join(f"{n}" for n, _ in inventory.summary(inv).values())]
            y += lh
        y += lh
    # torn bottom edge: a zigzag of transparency
    teeth = max(int(18 * s), 3)
    zig = " ".join(f"{x},{hpx - (teeth if (x // teeth) % 2 else 0)}" for x in range(0, wpx + teeth, teeth))
    cmd += ["-alpha", "set", "(", "-size", f"{wpx}x{hpx}", "xc:white", "-fill", "black", "-draw",
            f"polygon 0,{hpx} {zig} {wpx},{hpx}", ")", "-alpha", "off", "-compose", "copy_opacity", "-composite",
            str(path)]
    subprocess.run(cmd, check=True)
    return path, wpx, hpx


def render(name, pal, s):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    inv = inventory.load()

    # desk: theme background with a felt-like grain and a pool of light behind the receipt
    grain = value_noise(h, w, max(int(4 * s), 2), rng, octaves=3)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    pool = np.exp(-(((xx / w - 0.42) / 0.45) ** 2 + ((yy / h - 0.45) / 0.6) ** 2))
    desk = c["background"] * (0.75 + 0.15 * grain[..., None]) * (0.7 + 0.5 * pool[..., None])
    desk += c["accent"] * 0.02 * pool[..., None]

    tmp = ROOT / ".wip" / f"receipt--{name}@{s}.png"
    tmp.parent.mkdir(exist_ok=True)
    _, rw, rh = receipt_png(inv, pal, s, tmp)
    total = inventory.human(sum(i["bytes"] for i in inv))
    stamp_pt = int(64 * s)
    post = [
        "(", str(tmp), "-background", "none", "-rotate", "-4",
        "(", "+clone", "-background", "black", "-shadow", f"75x{int(28 * s)}+{int(30 * s)}+{int(40 * s)}", ")",
        "+swap", "-background", "none", "-layers", "merge", "+repage", ")",
        "-gravity", "center", "-geometry", f"-{int(330 * s)}+{int(20 * s)}", "-composite",
        # rubber stamp
        "(", "-size", f"{int(720 * s)}x{int(260 * s)}", "xc:none", "-fill", "none", "-stroke", pal["accent"],
        "-strokewidth", str(max(int(10 * s), 2)), "-draw",
        f"roundrectangle {int(12 * s)},{int(12 * s)} {int(708 * s)},{int(248 * s)} {int(30 * s)},{int(30 * s)}",
        "-stroke", "none", "-fill", pal["accent"], "-font", FONT, "-pointsize", str(stamp_pt), "-gravity", "center",
        "-annotate", f"+0-{int(36 * s)}", "INSTALLED", "-pointsize", str(int(40 * s)), "-annotate", f"+0+{int(52 * s)}",
        f"{len(inv)} ITEMS · {total}", "-channel", "A", "-evaluate", "multiply", "0.85", "+channel",
        "-rotate", "14", ")", "-gravity", "center", "-geometry", f"+{int(820 * s)}-{int(260 * s)}", "-composite",
    ]
    post += brand(pal, s, f"RECEIPT  ·  {len(inv)} ITEMS  ·  {total}  ·  {name.upper()}", corner="southeast")
    write(np.clip(desk, 0, 1), out_path("35-receipt", f"receipt--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
