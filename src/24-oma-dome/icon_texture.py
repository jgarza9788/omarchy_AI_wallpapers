"""Bake a tileable texture of Nerd Font app icons (white on black) for the Icon Dome.

Each icon is rendered once with ImageMagick and placed on a regular grid. Rows
alternate icon order so the pattern doesn't read as stripes. The result is a
greyscale mask; the Blender shader colours and brightens it.

Usage: python3 src/24-oma-dome/icon_texture.py  ->  src/24-oma-dome/icons.png
"""
import pathlib
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from appfield import APPS, CORE, Atlas  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
COLS, ROWS, CELL = 48, 24, 84          # 4032 x 2016 equirect-ish texture
GLYPH = 52


def main():
    rng = np.random.default_rng(24)
    atlas = Atlas()
    icons = APPS + CORE
    img = np.zeros((ROWS * CELL, COLS * CELL), np.float32)
    for r in range(ROWS):
        for c in range(COLS):
            g = atlas.get(icons[rng.integers(len(icons))], GLYPH)
            gh, gw = g.shape
            y0 = r * CELL + (CELL - gh) // 2
            x0 = c * CELL + (CELL - gw) // 2
            img[y0:y0 + gh, x0:x0 + gw] = np.maximum(img[y0:y0 + gh, x0:x0 + gw], g)
    out = HERE / "icons.png"
    raw = (img * 255).astype(np.uint8).tobytes()
    subprocess.run(["magick", "-size", f"{img.shape[1]}x{img.shape[0]}", "-depth", "8", "gray:-", str(out)],
                   input=raw, check=True)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
