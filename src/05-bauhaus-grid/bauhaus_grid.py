"""05 — Bauhaus Grid: flat geometric tiles built from the OMA logo's vocabulary.

The OMA mark is a circle, a notched square and a diamond cut into horizontal
bands. This generator writes an SVG of a 16x9 grid of 240px tiles: circles,
quarter-arcs, half-discs, diamonds, triangles and banded squares. Tiles get
denser towards the bottom-right, so the top-left stays calm for windows. A
recoloured OMA mark sits in the open space. The SVG is rasterised by
rsvg-convert, and the .svg is kept next to the PNG.

Usage: python3 src/05-bauhaus-grid/bauhaus_grid.py [--scheme nord|all] [--scale 0.25]
"""
import pathlib
import subprocess
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import H, W, out_path, scheme_args  # noqa: E402

SCHEMES = ["rose-pine", "nord", "lumon", "solitude", "white"]
T = 240  # tile size; 16 x 9 tiles at 3840x2160
COLS, ROWS = W // T, H // T


def oma_mark(x, y, size, colors):
    """The OMA logo paths (from assets/brand/oma-logo.svg) with recoloured bands."""
    k = size / 800
    stops = [0, 26.316, 26.316, 36.842, 36.842, 57.895, 57.895, 73.684, 73.684, 100]
    band = [colors[0], colors[0], colors[1], colors[1], colors[2], colors[2], colors[3], colors[3], colors[4], colors[4]]
    grad = "".join(f'<stop offset="{o}%" stop-color="{c}"/>' for o, c in zip(stops, band))
    return f'''<defs><linearGradient id="bands" x1="0" y1="250" x2="0" y2="550" gradientUnits="userSpaceOnUse">{grad}</linearGradient></defs>
<g transform="translate({x},{y}) scale({k})" fill="url(#bands)">
<path d="M283 285.21A149 149 0 1 0 283 514.79Z"/>
<path d="M283 262H536V326L462 400L536 474V536H283V514.79A149 149 0 0 0 283 285.21Z"/>
<path d="M536 326L610.5 251.5L759 400L610.5 548.5L536 474Z"/></g>'''


def motif(kind, x, y, s, fg, bg, rot):
    """One Bauhaus motif, clipped to its s x s cell at (x, y) by a nested <svg>."""
    body = _motif(kind, x, y, s, fg, bg, rot)
    return f'<svg x="{x}" y="{y}" width="{s}" height="{s}" viewBox="{x} {y} {s} {s}">{body}</svg>'


def _motif(kind, x, y, s, fg, bg, rot):
    cx, cy, r = x + s / 2, y + s / 2, s / 2
    tr = f'transform="rotate({rot} {cx} {cy})"'
    if kind == "circle":
        return f'<circle cx="{cx}" cy="{cy}" r="{r * 0.82}" fill="{fg}"/>'
    if kind == "quarter":
        return f'<path {tr} d="M{x} {y + s} L{x} {y} A{s} {s} 0 0 1 {x + s} {y + s} Z" fill="{fg}"/>'
    if kind == "half":
        return f'<path {tr} d="M{x} {cy} A{r} {r} 0 0 1 {x + s} {cy} Z" fill="{fg}"/>'
    if kind == "diamond":
        return f'<path d="M{cx} {y} L{x + s} {cy} L{cx} {y + s} L{x} {cy} Z" fill="{fg}"/>'
    if kind == "triangle":
        return f'<path {tr} d="M{x} {y} L{x + s} {y + s} L{x} {y + s} Z" fill="{fg}"/>'
    if kind == "bands":  # the OMA stripe motif
        h = s / 5
        return "".join(f'<rect x="{x}" y="{y + i * h}" width="{s}" height="{h * 0.62}" fill="{fg}"/>'
                       for i in range(5))
    if kind == "ring":
        return (f'<circle cx="{cx}" cy="{cy}" r="{r * 0.8}" fill="none" stroke="{fg}" stroke-width="{s * 0.12}"/>')
    if kind == "bite":  # square with a circular bite, like the logo's middle piece
        return (f'<rect x="{x}" y="{y}" width="{s}" height="{s}" fill="{fg}"/>'
                f'<circle {tr} cx="{x}" cy="{cy}" r="{r * 0.7}" fill="{bg}"/>')
    if kind == "dots":
        g = s / 4
        return "".join(f'<circle cx="{x + g * (i + 0.5)}" cy="{y + g * (j + 0.5)}" r="{g * 0.18}" fill="{fg}"/>'
                       for i in range(4) for j in range(4))
    return ""


def build_svg(name, pal):
    rng = np.random.default_rng(1919)  # Bauhaus founding year
    light = pal["mode"] == "light"
    bg = pal["background"]
    alt = pal.get("lighter_background", bg) if not light else pal.get("dark_background", bg)
    ink = pal["foreground"]
    shapes = [pal["accent"], pal["red"], pal["yellow"], pal["blue"], ink]
    kinds = ["circle", "quarter", "quarter", "half", "diamond", "triangle", "bands", "ring", "bite", "dots"]

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
           f'<rect width="{W}" height="{H}" fill="{bg}"/>']
    used = np.zeros((ROWS, COLS), bool)

    def density(c, r):
        # 0 at the top-left, 1 at the bottom-right, with a soft diagonal front
        d = (c / (COLS - 1)) * 0.62 + (r / (ROWS - 1)) * 0.38
        return float(np.clip((d - 0.38) / 0.35, 0, 1))

    # reserve the OMA mark area (bottom-left calm zone)
    used[5:9, 0:5] = True

    # a few big 2x2 feature tiles first
    for _ in range(14):
        c, r = int(rng.integers(0, COLS - 1)), int(rng.integers(0, ROWS - 1))
        if used[r:r + 2, c:c + 2].any() or rng.random() > density(c, r) ** 0.7:
            continue
        used[r:r + 2, c:c + 2] = True
        x, y = c * T, r * T
        out.append(f'<rect x="{x}" y="{y}" width="{2 * T}" height="{2 * T}" fill="{alt}"/>')
        out.append(motif(rng.choice(["circle", "quarter", "half", "bands", "bite"]), x, y, 2 * T,
                         shapes[rng.integers(len(shapes))], alt, int(rng.integers(4)) * 90))

    for r in range(ROWS):
        for c in range(COLS):
            if used[r, c] or rng.random() > density(c, r):
                continue
            x, y = c * T, r * T
            tile_bg = alt if rng.random() < 0.45 else bg
            if tile_bg != bg:
                out.append(f'<rect x="{x}" y="{y}" width="{T}" height="{T}" fill="{tile_bg}"/>')
            out.append(motif(rng.choice(kinds), x, y, T, shapes[rng.integers(len(shapes))],
                             tile_bg, int(rng.integers(4)) * 90))

    # faint construction grid over everything
    grid = pal.get("selection", alt)
    out.append(f'<g stroke="{grid}" stroke-width="1.5" opacity="0.35">')
    out += [f'<line x1="{c * T}" y1="0" x2="{c * T}" y2="{H}"/>' for c in range(1, COLS)]
    out += [f'<line x1="0" y1="{r * T}" x2="{W}" y2="{r * T}"/>' for r in range(1, ROWS)]
    out.append("</g>")

    # OMA mark + caption in the calm zone
    band_cols = [pal.get("bright_foreground", ink), pal["yellow"], pal["accent"], pal["red"], pal["blue"]]
    out.append(oma_mark(T * 1 - 60, T * 6 - 280, 3 * T + 120, band_cols))
    out.append(f'<text x="{T * 1 + 40}" y="{T * 8 - 20}" font-family="SpaceMono Nerd Font Mono" font-size="44" '
               f'letter-spacing="10" fill="{pal.get("dark_foreground", ink)}">OMARCHY · {name.upper()}</text>')
    out.append("</svg>")
    return "\n".join(out)


def render(name, pal, s):
    png = out_path("05-bauhaus-grid", f"bauhaus-grid--{name}", s)
    svg = png.with_suffix(".svg")
    svg.parent.mkdir(parents=True, exist_ok=True)
    svg.write_text(build_svg(name, pal))
    subprocess.run(["rsvg-convert", "-w", str(int(W * s)), "-h", str(int(H * s)), str(svg), "-o", str(png)],
                   check=True)
    print(f"wrote {png}")


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for n in names:
        render(n, pals[n], scale)
