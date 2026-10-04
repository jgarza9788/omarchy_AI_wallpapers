"""04 — Pixel Dusk: a 480x270 pixel-art landscape, dithered to the theme's palette by GIMP.

The OMA logo is the setting sun (synthwave stripes cut through it), behind
layered ridges with atmospheric haze and a rippling lake reflection. numpy
paints a smooth-colour scene; GIMP then converts it to indexed colour using
*only* the theme's colours (Floyd–Steinberg dithering) and scales it x8 with
nearest-neighbour so every pixel stays crisp at 3840x2160.

Usage: python3 src/04-pixel-dusk/pixel_dusk.py [--scheme gruvbox|all] [--scale 0.25]
"""
import os
import pathlib
import subprocess
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import BRAND, ROOT, hex2arr, load_alpha, out_path, ramp, save_rgb, scheme_args  # noqa: E402

SCHEMES = ["gruvbox", "catppuccin", "everforest", "ethereal", "last-horizon"]
PW, PH = 480, 270
HORIZON = 178  # y of the lake line in pixel space


def ridge(rng, base, amp, roughness):
    x = np.arange(PW, dtype=np.float32)
    y = np.full(PW, base, np.float32)
    for octave in range(6):
        f = 2 ** octave * 1.3 / PW  # cycles per pixel
        y += amp * roughness ** octave * np.sin(x * f * np.pi * 2 + rng.uniform(0, 6.28))
    return y


def mix(a, b, t):
    return a * (1 - t) + b * t


def scene(pal):
    rng = np.random.default_rng(1982)
    light = pal["mode"] == "light"
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    ink = c["foreground"] if light else c.get("darker_background", c["background"])
    yy, xx = np.mgrid[0:PH, 0:PW].astype(np.float32)

    # sky: top -> mid -> horizon glow
    sky_top = c["background"] if light else c.get("darker_background", c["background"])
    sky = ramp([sky_top, mix(sky_top, c["blue"], 0.45), mix(c["magenta"], c["red"], 0.4),
                mix(c["orange"] if "orange" in c else c["yellow"], c["yellow"], 0.4)],
               (yy / HORIZON) ** 1.25)
    img = sky.copy()

    # stars (dark themes only)
    if not light:
        n = 160
        sx, sy = rng.integers(0, PW, n), rng.integers(0, int(HORIZON * 0.55), n)
        b = rng.random(n)
        for x, y, v in zip(sx, sy, b):
            img[y, x] = mix(img[y, x], c.get("bright_foreground", c["foreground"]), 0.4 + 0.6 * v)

    # sun: OMA logo silhouette with synthwave stripes, gradient yellow -> red -> magenta
    logo_w, logo_h = 320, 320
    mark = load_alpha(BRAND / "oma-logo.png", logo_w, logo_h)
    sun = np.zeros((PH, PW), np.float32)
    top = HORIZON - 195  # logo art sits in the middle of its square canvas
    x0 = (PW - logo_w) // 2
    y_end = min(top + logo_h, PH)
    sun[max(top, 0):y_end, x0:x0 + logo_w] = mark[max(-top, 0): y_end - top]
    sun_top = top + int(logo_h * 0.31)  # the mark spans ~31%..69% of its square canvas
    rel = np.clip((yy - sun_top) / (HORIZON - sun_top), 0, 1)  # 0 top of sun -> 1 horizon
    period = 10 - 5 * rel
    stripes = ((yy - HORIZON) % np.maximum(period, 2)) < ((rel - 0.4) * period * 0.9)
    sun = np.where(stripes & (rel > 0.45), 0, sun)
    sun_col = ramp([c["bright_yellow"] if "bright_yellow" in c else c["yellow"], c["yellow"],
                    c["orange"] if "orange" in c else c["red"], c["red"], c["magenta"]], rel)
    # soft glow around the sun
    glow = np.exp(-(((xx - PW / 2) / 120) ** 2 + ((yy - (HORIZON - 40)) / 70) ** 2))
    img = mix(img, c["yellow"], (glow * 0.25)[..., None])
    img = mix(img, sun_col, sun[..., None])

    # ridges: far (hazy, bluish) -> near (ink)
    haze = mix(c["magenta"], c["blue"], 0.5)
    for base, amp, rough, t in [(146, 14, 0.55, 0.3), (158, 10, 0.5, 0.55), (167, 7, 0.45, 0.8), (174, 4, 0.4, 1.0)]:
        h = ridge(rng, base, amp, rough)
        mask = yy >= h[None, :]
        col = mix(mix(haze, sky_top, 0.25), ink, t)
        # rim light on ridge crests
        crest = (yy - h[None, :] < 1.5) & mask
        img = np.where(mask[..., None], col, img)
        img = np.where(crest[..., None], mix(col, c["yellow"], 0.35 * (1 - t) + 0.1), img)

    # lake: mirrored scene with ripples + darkening
    water = HORIZON + 2
    depth = np.arange(PH - water, dtype=np.float32)
    src_y = np.clip(water - 1 - depth, 0, PH - 1).astype(int)
    ripple = (np.sin(depth[:, None] * 0.9 + xx[water:] * 0.12) * (1 + depth[:, None] * 0.08)).astype(int)
    src_x = np.clip(xx[water:].astype(int) + ripple, 0, PW - 1)
    refl = img[src_y[:, None], src_x]
    dark = np.clip(depth / (PH - water), 0, 1)[:, None, None]
    img[water:] = mix(refl, ink, 0.5 + 0.4 * dark)
    img[HORIZON:water] = mix(ink, c["yellow"], 0.15)
    # foreground shore silhouette
    shore = ridge(rng, PH - 6, 4, 0.5)
    img = np.where((yy >= shore[None, :])[..., None], ink, img)
    return img


def theme_palette(pal):
    keys = ["background", "foreground", "darker_background", "black", "white", "red", "green",
            "yellow", "blue", "magenta", "cyan", "orange", "bright_red", "bright_green",
            "bright_yellow", "bright_blue", "bright_magenta", "bright_cyan", "accent"]
    seen = []
    for k in keys:
        v = pal.get(k)
        if v and v.lower() not in seen:
            seen.append(v.lower())
    return seen


def render(name, pal, s):
    tmp = ROOT / ".wip" / f"pixel-{name}"
    tmp.mkdir(parents=True, exist_ok=True)
    src = tmp / "scene.png"
    save_rgb(scene(pal), src)
    out = out_path("04-pixel-dusk", f"pixel-dusk--{name}", s)
    out.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, WP_IN=str(src), WP_OUT=str(out), WP_COLORS=",".join(theme_palette(pal)),
               WP_W=str(int(3840 * s)), WP_H=str(int(2160 * s)), WP_NAME=f"wp-pixel-dusk-{name}")
    r = subprocess.run(["gimp", "-i", "--quit", "--batch-interpreter", "python-fu-eval",
                        "-b", f"exec(open('{HERE / 'dither.py'}').read())"],
                       env=env, capture_output=True, text=True)
    if r.returncode or not out.exists():
        sys.exit(f"GIMP failed:\n{r.stdout}\n{r.stderr}")
    print(f"wrote {out}")


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for n in names:
        render(n, pals[n], scale)
