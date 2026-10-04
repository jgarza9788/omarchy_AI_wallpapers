"""22 — Paper Terrain: Topography (02) remade as a layered paper cut.

The same terrain field (fBm noise plus the Omarchy wordmark as a mesa) is cut into
stacked sheets of paper. Each sheet, from the bottom up, casts a soft offset
shadow onto everything beneath it and has a thin highlight along its lit edge.
Fine fibre grain finishes the paper. Sheet colours step through tones drawn from
the theme, so light themes read as card stock and dark themes as felt.

Inspired by the layered-paper and folded-paper backgrounds that ship with
Omarchy's white and vantablack themes.

Usage: python3 src/22-paper-terrain/paper_terrain.py [--scheme white|all] [--scale 0.25]
"""
import importlib.util
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import FONTS, H, W, box_blur, hex2arr, out_path, ramp, save_rgb, scheme_args  # noqa: E402

_spec = importlib.util.spec_from_file_location("topography", HERE.parent / "02-topography" / "topography.py")
topography = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(topography)

SCHEMES = ["white", "rose-pine", "nord", "everforest"]
SHEETS = 13


def render(name, pal, s):
    w, h = int(W * s), int(H * s)
    field = topography.terrain_field(w, h, s, terrain_gain=0.62, halo_gain=0.12)  # letters clearly on top
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    light = pal["mode"] == "light"
    bg, fg, acc = c["background"], c["foreground"], c["accent"]
    if light:   # card stock: from the background colour toward muted accents
        stops = [bg * 0.92, bg, bg * 0.7 + acc * 0.3, bg * 0.55 + c["blue"] * 0.45, bg * 0.6 + c["red"] * 0.4,
                 bg * 0.55 + acc * 0.45]
    else:       # felt: dark to rich colour
        stops = [c.get("darker_background", bg), bg, bg * 0.6 + c["blue"] * 0.4, bg * 0.5 + acc * 0.5,
                 bg * 0.45 + c["green"] * 0.55, bg * 0.4 + c["yellow"] * 0.6]
    cols = ramp(stops, np.linspace(0, 1, SHEETS))

    off = np.array([10, 14]) * s * 1.6            # light from the top-left -> shadow toward bottom-right
    img = np.broadcast_to(cols[0], (h, w, 3)).copy()
    for k in range(1, SHEETS):
        mask = (field >= k / SHEETS).astype(np.float32)
        if mask.sum() == 0:
            continue
        # soft shadow of this sheet on everything below it
        sh = np.roll(mask, (int(off[1]), int(off[0])), axis=(0, 1))
        sh = box_blur(sh, 14 * s * 1.5) * (1 - mask)
        img *= (1 - 0.2 * sh)[..., None]
        # the sheet itself, with a lit rim along its upper-left edge
        edge = np.clip(mask - np.roll(mask, (int(3 * s + 1), int(3 * s + 1)), axis=(0, 1)), 0, 1)
        edge = box_blur(edge, max(1.2 * s, 1), passes=1)
        sheet = cols[k] * (1 + 0.18 * edge[..., None])
        img = img * (1 - mask[..., None]) + sheet * mask[..., None]

    # paper fibre: fine grain + faint long fibres
    rng = np.random.default_rng(3)
    grain = rng.normal(0, 0.012, (h, w)).astype(np.float32)
    fibres = box_blur(rng.normal(0, 1, (h, w)).astype(np.float32), 1) * 0.01
    img = img * (1 + grain + fibres)[..., None]

    font = str(FONTS / "SpaceMono" / "SpaceMonoNerdFontMono-Regular.ttf")
    dim = pal.get("dark_foreground", pal["foreground"])
    m = int(110 * s)
    post = ["-font", font, "-pointsize", str(max(int(24 * s), 7)), "-fill", dim, "-kerning", str(max(int(6 * s), 1)),
            "-gravity", "southwest", "-annotate", f"+{m}+{m}", f"PAPER TERRAIN  ·  {SHEETS} SHEETS  ·  {name.upper()}"]
    save_rgb(np.clip(img, 0, 1), out_path("22-paper-terrain", f"paper-terrain--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
