"""03 — Glyph Rain: a terminal-style matrix of Nerd Font icons around the ASCII Omarchy logo.

Pipeline:
  1. numpy decides columns, falling "drops" and per-glyph opacity for 3 depth layers
  2. each layer is an ImageMagick MVG draw file -> transparent PNG (far layers blurred)
  3. the ASCII logo (/usr/share/omarchy/logo.txt) + a shell prompt are rendered in Nerd Font
  4. GIMP (Python-Fu batch, glow.py) composites logo + neon glow onto the rain

Usage: python3 src/03-glyph-rain/glyph_rain.py [--scheme hackerman|all] [--scale 0.25]
"""
import os
import pathlib
import subprocess
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import FONTS, H, ROOT, W, box_blur, hex2arr, out_path, save_rgb, scheme_args  # noqa: E402

SCHEMES = ["hackerman", "tokyo-night", "retro-82", "miasma", "ristretto"]
FONT = FONTS / "Iosevka" / "IosevkaNerdFontMono-Regular.ttf"
FONT_BOLD = FONTS / "Iosevka" / "IosevkaNerdFontMono-Bold.ttf"
LOGO_TXT = pathlib.Path("/usr/share/omarchy/logo.txt")

ICONS = [chr(c) for c in (
    0xF303, 0xF17C, 0xE702, 0xF418, 0xF489, 0xE62B, 0xE73C, 0xE7A8, 0xF308, 0xE627,
    0xE74E, 0xE620, 0xF359, 0xF08C7, 0xF120, 0xE795, 0xF0E7, 0xF09B, 0xE718, 0xE7C5,
    0xF013, 0xF233, 0xE615, 0xE61D, 0xE737, 0xE606, 0xF0219, 0xF484)]
CHARS = ICONS * 3 + list("0123456789abcdef{}[]<>/\\|=+*#$%&~")

# (point size, column spacing factor, opacity scale, blur sigma) far -> near
LAYERS = [(26, 1.25, 0.35, 2.2), (40, 1.35, 0.6, 0.8), (60, 1.6, 1.0, 0.0)]


def glyph_atlas(pt, cache):
    """Render every glyph once as an alpha mask (cell = pt*1.0 x pt*1.25)."""
    cw, ch = int(pt * 1.0), int(pt * 1.25)
    atlas = []
    for g in CHARS:
        key = cache / f"g{pt}_{ord(g):x}.gray"
        if not key.exists():
            raw = subprocess.run(
                ["magick", "-size", f"{cw}x{ch}", "xc:black", "-font", str(FONT), "-pointsize", str(pt),
                 "-fill", "white", "-gravity", "center", "-annotate", "+0+0", g,
                 "-depth", "8", "gray:-"], check=True, capture_output=True).stdout
            key.write_bytes(raw)
        atlas.append(np.frombuffer(key.read_bytes(), np.uint8).reshape(ch, cw).astype(np.float32) / 255)
    return atlas


def rain_layer(pal, s, rng, pt, spacing, op, fade, cache):
    """Return (rgb premultiplied, alpha) float arrays for one depth layer of falling glyphs."""
    pt = max(int(pt * s), 6)
    atlas = glyph_atlas(pt, cache)
    gh, gw = atlas[0].shape
    w, h = int(W * s), int(H * s)
    cw, ch = pt * spacing, pt * 1.25
    ncols, nrows = int(w / cw) + 1, int(h / ch) + 2
    colors = [hex2arr(pal[k]) for k in ("accent", "green", "cyan", "blue", "magenta", "bright_green")]
    head = hex2arr(pal.get("bright_foreground", pal["foreground"]))
    rgb = np.zeros((h + gh, w + gw, 3), np.float32)
    alpha = np.zeros((h + gh, w + gw), np.float32)
    for c in range(ncols):
        x = int(c * cw + rng.uniform(-0.1, 0.1) * cw)
        col_color = colors[rng.integers(len(colors))] if rng.random() < 0.35 else colors[0]
        drops = [(rng.uniform(-0.2, 1.2) * nrows, rng.uniform(6, 26)) for _ in range(rng.integers(1, 4))]
        for r in range(nrows):
            y = int(r * ch)
            a, is_head = 0.05, False  # 0.05 = faint static texture
            for hy, length in drops:
                d = hy - r
                if 0 <= d < length:
                    a = max(a, (1 - d / length) ** 1.6)
                    if d < 1:
                        is_head, a = True, 1.0
            a *= op * fade(x / w, y / h)
            if a < 0.02 or x < 0 or y + gh > h + gh or x + gw > w + gw:
                continue
            m = atlas[rng.integers(len(atlas))] * a
            color = head if is_head else col_color
            # "over" compositing of glyph onto the layer
            sl = (slice(y, y + gh), slice(x, x + gw))
            rgb[sl] = rgb[sl] * (1 - m[..., None]) + color * m[..., None]
            alpha[sl] = alpha[sl] * (1 - m) + m
    return rgb[:h, :w], alpha[:h, :w]


def clearing(cx=0.5, cy=0.47, rx=0.36, ry=0.24):
    """Fade the rain inside an ellipse so the logo reads."""
    def fade(u, v):
        d = ((u - cx) / rx) ** 2 + ((v - cy) / ry) ** 2
        return float(np.clip((d - 0.55) / 0.6, 0.08, 1.0))
    return fade


def render(name, pal, s):
    rng = np.random.default_rng(42)
    w, h = int(W * s), int(H * s)
    tmp = ROOT / ".wip" / f"rain-{name}"
    tmp.mkdir(parents=True, exist_ok=True)
    bg, dark = pal["background"], pal.get("darker_background", pal["background"])

    # 1+2. rain layers composited (far -> near) over a vertical gradient
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    img = np.broadcast_to(hex2arr(bg) * (1 - t) + hex2arr(dark) * t, (h, w, 3)).copy()
    for pt, sp, op, blur in LAYERS:
        rgb, alpha = rain_layer(pal, s, rng, pt, sp, op, clearing(), tmp.parent / "atlas")
        if blur:
            r = blur * s * 4
            rgb = np.stack([box_blur(rgb[..., i], r) for i in range(3)], -1)
            alpha = box_blur(alpha, r)
        img = img * (1 - alpha[..., None]) + rgb
    rain = tmp / "rain.png"
    save_rgb(img, rain)

    # 3. ASCII logo + prompt on black (blended with screen/addition, so black = no-op)
    logo_pt = max(int(46 * s), 8)
    logo = tmp / "logo.png"
    prompt = f"  ~/omarchy   main  ❯ {name} █"
    subprocess.run([
        "magick", "-size", f"{w}x{h}", "xc:black",
        "-font", str(FONT_BOLD), "-pointsize", str(logo_pt), "-interline-spacing", str(-int(logo_pt * 0.12)),
        "-fill", pal["accent"], "-gravity", "center",
        "-annotate", f"+0-{int(90 * s)}", LOGO_TXT.read_text().rstrip("\n"),
        "-font", str(FONT), "-pointsize", str(max(int(40 * s), 6)),
        "-fill", pal.get("bright_foreground", pal["foreground"]),
        "-annotate", f"+0+{int(330 * s)}", prompt,
        str(logo)], check=True)

    # 4. GIMP: glow + composite
    out = out_path("03-glyph-rain", f"glyph-rain--{name}", s)
    out.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, WP_BASE=str(rain), WP_LOGO=str(logo), WP_OUT=str(out), WP_SCALE=str(s))
    subprocess.run(["gimp", "-i", "--quit", "--batch-interpreter", "python-fu-eval",
                    "-b", f"exec(open('{HERE / 'glow.py'}').read())"],
                   env=env, check=True, capture_output=True)
    print(f"wrote {out}")


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for n in names:
        render(n, pals[n], scale)
