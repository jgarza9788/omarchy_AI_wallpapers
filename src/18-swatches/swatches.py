"""18 — Swatches: a theme's real colours as overlapping shapes.

Riffs on the overlapping-capsule palette wallpapers on Wallhaven's minimalism
toplist, but every swatch is a real colour from the Omarchy theme. They're sorted
by luminance, brightest in front, each tucked behind the one before with a soft
shadow, with its hex code set beneath in Space Mono. The shape changes per theme:
capsules, the OMA circle (O), the notched square (M) or the diamond (A), using the
exact logo outlines.

Usage: python3 src/18-swatches/swatches.py [--scheme gruvbox|all] [--scale 0.25]
"""
import pathlib
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import oma_shapes  # noqa: E402
from common import H, W, out_path, palettes, scheme_args  # noqa: E402

SHAPE = {"gruvbox": "capsule", "tokyo-night": "A", "rose-pine": "O", "kanagawa": "M", "everforest": "capsule"}
SCHEMES = list(SHAPE)
KEYS = ["foreground", "yellow", "orange", "red", "magenta", "blue", "cyan", "green", "accent", "brown", "muted"]


def luminance(hx):
    r, g, b = palettes.rgb(hx)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def shape_path(kind, cx, cy, size):
    if kind == "capsule":
        w, h = size * 0.42, size
        return (f'<rect x="{cx - w / 2:.1f}" y="{cy - h / 2:.1f}" width="{w:.1f}" height="{h:.1f}" '
                f'rx="{w / 2:.1f}"/>')
    pts = oma_shapes.normalized(oma_shapes.PIECES[kind](), size)
    d = "M" + " L".join(f"{cx + x:.1f} {cy - y:.1f}" for x, y in pts) + " Z"
    return f'<path d="{d}"/>'


def build(name, pal):
    seen, cols = set(), []
    for k in KEYS:
        v = pal.get(k)
        if v and v.lower() not in seen and abs(luminance(v) - luminance(pal["background"])) > 0.06:
            seen.add(v.lower())
            cols.append(v)
    cols = sorted(cols, key=luminance, reverse=True)[:9]
    kind = SHAPE.get(name, "capsule")
    n = len(cols)
    size = H * (0.42 if kind == "capsule" else 0.3)   # logo pieces are wider than capsules
    step = size * (0.3 if kind == "capsule" else 0.46)
    total = step * (n - 1) + size * (0.42 if kind == "capsule" else 1)
    x0 = W / 2 - total / 2 + (size * 0.21 if kind == "capsule" else size / 2)
    cy = H * 0.47
    dim = pal.get("dark_foreground", pal["foreground"])
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
           '<defs><filter id="sh" x="-50%" y="-50%" width="200%" height="200%">'
           '<feDropShadow dx="-18" dy="10" stdDeviation="26" flood-color="#000" flood-opacity="0.45"/></filter></defs>',
           f'<rect width="{W}" height="{H}" fill="{pal["background"]}"/>']
    # draw back to front: the darkest (last) first
    for i in reversed(range(n)):
        cx = x0 + i * step
        out.append(f'<g fill="{cols[i]}" filter="url(#sh)">{shape_path(kind, cx, cy, size)}</g>')
    for i in range(n):
        cx = x0 + i * step
        out.append(f'<text x="{cx:.1f}" y="{cy + size * 0.5 + 90:.1f}" text-anchor="middle" '
                   f'font-family="SpaceMono Nerd Font Mono" font-size="26" fill="{dim}">{cols[i].lower()}</text>')
    out.append(f'<text x="{W - 110}" y="{H - 110}" text-anchor="end" font-family="SpaceMono Nerd Font Mono" '
               f'font-size="26" letter-spacing="8" fill="{dim}">OMARCHY · {name.upper()} · {n} COLORS</text>')
    out.append("</svg>")
    return "\n".join(out)


def render(name, pal, s):
    png = out_path("18-swatches", f"swatches--{name}", s)
    svg = png.with_suffix(".svg")
    svg.parent.mkdir(parents=True, exist_ok=True)
    svg.write_text(build(name, pal))
    subprocess.run(["rsvg-convert", "-w", str(int(W * s)), "-h", str(int(H * s)), str(svg), "-o", str(png)], check=True)
    print(f"wrote {png}")


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
