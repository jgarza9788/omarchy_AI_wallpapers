"""10 — Sundial: a wallpaper made of time.

A top-down architectural plan with a gnomon, an engraved hour dial, a line of
rods and a slatted pergola. One frame is rendered for each hour of the day.
Shadows come from the real solar position (your latitude from Omarchy's weather
setting, today's solar declination). The sun's elevation also picks the Omarchy
theme: white when high, flexoki-light, rose-pine for low sun, catppuccin (dawn) /
ristretto (dusk) twilight, then ethereal and tokyo-night. After sunset the gnomon
becomes a lamp and everything throws radial shadows away from it.
The dial's hour lines are where the gnomon's shadow falls at each hour today.
sundial-tick.sh shows the frame for the current hour (see README to schedule it).

Usage: python3 src/10-sundial/sundial.py [--hours all|14] [--scale 0.25] [--lat 35]
"""
import argparse
import datetime as dt
import json
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import FONTS, H, W, box_blur, hex2arr, out_path, palettes, save_rgb  # noqa: E402

def theme_for(hour, el):
    """The sun picks the colour scheme: light themes while it's up, dark ones after."""
    morning = hour < 12
    if el > 35:
        return "white"
    if el > 15:
        return "flexoki-light"
    if el > 0:
        return "rose-pine"
    if el > -12:
        return "catppuccin" if morning else "ristretto"
    if el > -24:
        return "ethereal"
    return "tokyo-night"


def latitude(default=35.0):
    f = pathlib.Path.home() / ".local/state/omarchy/settings/weather.json"
    try:
        return float(json.loads(f.read_text())["latitude"])
    except Exception:
        return default


def sun_position(hour, lat, day=None):
    """Elevation and azimuth (degrees, azimuth clockwise from north) at local solar time."""
    day = day or dt.date.today()
    doy = day.timetuple().tm_yday
    decl = math.radians(23.44) * math.sin(2 * math.pi * (doy - 81) / 365)
    ha = math.radians(15 * (hour - 12))
    phi = math.radians(lat)
    sin_el = math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(ha)
    el = math.asin(sin_el)
    az = math.atan2(-math.sin(ha) * math.cos(decl),
                    math.cos(phi) * math.sin(decl) - math.sin(phi) * math.cos(decl) * math.cos(ha))
    return math.degrees(el), math.degrees(az) % 360


def palette_at(theme, pals):
    p = pals[theme]
    return {k: hex2arr(p[k]) for k in ("background", "foreground", "accent", "yellow", "blue", "red", "orange")
            if k in p}


def scene(s):
    """Objects in 4K design pixels: rods (x, y, radius, height) and pergola slats."""
    rods = [(0.30 * W, 0.56 * H, 16, 620)]                       # the gnomon
    rng = np.random.default_rng(12)
    for i in range(9):                                            # a diagonal line of rods
        t = i / 8
        rods.append((0.06 * W + t * 0.16 * W, 0.92 * H - t * 0.75 * H, 9, 120 + 260 * rng.random()))
    px0, px1, py0, py1 = 0.58 * W, 0.93 * W, 0.16 * H, 0.82 * H  # pergola
    for x in (px0, px1):
        for y in (py0, py1):
            rods.append((x, y, 22, 300))
    slats = [(px0 - 30, y, px1 + 30, y + 22, 300) for y in np.arange(py0, py1, 74)]
    beams = [(px0 - 12, py0 - 50, px0 + 12, py1 + 50, 312), (px1 - 12, py0 - 50, px1 + 12, py1 + 50, 312)]
    return [(x * s, y * s, r * s, h * s) for x, y, r, h in rods], \
           [(a * s, b * s, c * s, d * s, h * s) for a, b, c, d, h in slats + beams]


def render_hour(hour, pals, lat, s):
    w, h = int(W * s), int(H * s)
    el, az = sun_position(hour, lat)
    theme = theme_for(hour, el)
    pal = palette_at(theme, pals)
    day = float(np.clip(math.sin(math.radians(el)) * 4, 0, 1))
    night = el <= 0
    el_cast = max(el, 3.0)
    strength = 0.55 * day + 0.12
    # shadow vector per unit height, screen coords (north = up)
    k = min(1 / math.tan(math.radians(el_cast)), 8.0)
    sx, sy = -math.sin(math.radians(az)) * k, math.cos(math.radians(az)) * k

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    shadow = np.zeros((h, w), np.float32)
    rods, slats = scene(s)
    LX, LY, LH = rods[0][0], rods[0][1], rods[0][3] * 1.08  # night: lamp atop the gnomon
    for x, y, r, ht in rods[1:] if night else rods:
        if night:  # radial shadow away from the lamp, length ht*d/(LH-ht)
            f = min(ht / max(LH - ht, 1e-3), 6.0)
            tx, ty = x + (x - LX) * f, y + (y - LY) * f
        else:      # parallel sunlight
            tx, ty = x + sx * ht, y + sy * ht
        vx, vy = tx - x, ty - y
        L2 = vx * vx + vy * vy + 1e-6
        t = np.clip(((xx - x) * vx + (yy - y) * vy) / L2, 0, 1)
        d = np.hypot(xx - (x + t * vx), yy - (y + t * vy))
        shadow = np.maximum(shadow, np.clip(r * (1 + t * night) - d + 0.5, 0, 1) * (1 - 0.35 * t))
    for x0, y0, x1, y1, ht in slats:
        if night:  # perspective projection from the lamp: scale about it
            f = LH / max(LH - ht, 1e-3)
            X0, X1 = LX + (x0 - LX) * f, LX + (x1 - LX) * f
            Y0, Y1 = LY + (y0 - LY) * f, LY + (y1 - LY) * f
        else:
            X0, X1, Y0, Y1 = x0 + sx * ht, x1 + sx * ht, y0 + sy * ht, y1 + sy * ht
        inside = (xx >= min(X0, X1)) & (xx <= max(X0, X1)) & (yy >= min(Y0, Y1)) & (yy <= max(Y0, Y1))
        shadow = np.maximum(shadow, inside * 0.9)
    shadow = box_blur(shadow, max(2.5 * s * 4 * (1.3 - day), 1))

    bg = pal["background"]
    fg = pal["foreground"]
    lightness = float(bg.mean())
    shade_col = bg * 0.45 + pal["blue"] * 0.12 if lightness > 0.5 else bg * 0.35
    warm = pal.get("orange", pal["yellow"])
    golden = float(np.clip(1 - abs(el - 6) / 10, 0, 1)) if el > 0 else 0.0
    ground = bg * (1 - 0.12 * golden) + warm * 0.12 * golden
    rng = np.random.default_rng(5)
    grain = (1 + rng.normal(0, 0.015, (h, w))).astype(np.float32)[..., None]
    img = ground[None, None] * grain
    if night:  # warm pool of lamplight, blocked where shadowed
        dist = np.hypot(xx - LX, yy - LY) / (900 * s)
        lamp = (1 / (1 + dist * dist * 2.5))[..., None] * (1 - shadow[..., None] * 0.85)
        img = img * 0.75 + (warm * 0.55 + fg * 0.15) * lamp * 0.55
    else:
        img = img * (1 - (shadow * strength)[..., None]) + shade_col * (shadow * strength)[..., None]

    # engraved dial: hour lines at today's shadow azimuth for each daylight hour
    gx, gy = rods[0][0], rods[0][1]
    R = 520 * s
    engrave = np.zeros((h, w), np.float32)
    labels = []
    for hr in range(5, 20):
        e, a = sun_position(hr, lat)
        if e <= 0:
            continue
        ang = math.radians(a + 180)
        dx, dy = math.sin(ang), -math.cos(ang)
        t = np.clip((xx - gx) * dx + (yy - gy) * dy, R * 0.55, R)
        d = np.hypot(xx - (gx + t * dx), yy - (gy + t * dy))
        engrave = np.maximum(engrave, np.clip(1.6 * s * 4 / 4 + 0.5 - d, 0, 1))
        labels.append((gx + dx * (R + 46 * s), gy + dy * (R + 46 * s), f"{hr:02d}"))
    ring = np.abs(np.hypot(xx - gx, yy - gy) - R * 1.02)
    engrave = np.maximum(engrave, np.clip(1.2 + 0.5 - ring, 0, 1))
    img = img * (1 - engrave[..., None] * 0.35) + fg * engrave[..., None] * 0.35

    # object tops: rods as discs lit from the sun side, slats as bars
    lx, ly = -sx / (k + 1e-6), -sy / (k + 1e-6)
    top_col = fg * 0.75 + bg * 0.25
    for x0, y0, x1, y1, _ in slats:
        m = ((xx >= x0) & (xx <= x1) & (yy >= y0) & (yy <= y1)).astype(np.float32)[..., None]
        img = img * (1 - m) + (top_col * 0.92 + pal["yellow"] * 0.08 * day) * m
    for i, (x, y, r, _) in enumerate(rods):
        d = np.hypot(xx - x, yy - y)
        m = np.clip(r - d + 0.5, 0, 1)[..., None]
        hl = np.clip(((xx - x) * lx + (yy - y) * ly) / (r + 1e-6), -1, 1)[..., None]
        c = (pal["accent"] if i == 0 else top_col) * (0.85 + 0.25 * hl * day)
        if i == 0 and night:
            c = warm * 0.5 + 0.5
            halo = np.exp(-(d / (60 * s)) ** 2)[..., None]
            img = img + warm * halo * 0.6
        img = img * (1 - m) + c * m

    # labels: hour numerals + a small legend
    font = str(FONTS / "SpaceMono" / "SpaceMonoNerdFontMono-Regular.ttf")
    pt = max(int(26 * s), 7)
    dim = "#%02x%02x%02x" % tuple(int(v * 255) for v in (fg * 0.6 + bg * 0.4))
    post = ["-font", font, "-pointsize", str(pt), "-fill", dim, "-gravity", "northwest"]
    for x, y, txt in labels:
        post += ["-annotate", f"+{int(x - pt * 0.6)}+{int(y - pt * 0.6)}", txt]
    sun_txt = f"sun {el:+.0f}° / az {az:.0f}°" if not night else f"sun {el:+.0f}° · lamplight"
    post += ["-gravity", "southeast", "-annotate", f"+{int(110 * s)}+{int(110 * s)}",
             f"{hour:02d}:00  ·  {sun_txt}  ·  {theme}"]
    save_rgb(np.clip(img, 0, 1), out_path("10-sundial", f"sundial--{hour:02d}h", s), post)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", default="all")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--lat", type=float, default=None)
    args = ap.parse_args()
    lat = args.lat if args.lat is not None else latitude()
    hours = range(24) if args.hours == "all" else [int(x) for x in args.hours.split(",")]
    pals = palettes.load()
    for hr in hours:
        render_hour(hr, pals, lat, args.scale)


if __name__ == "__main__":
    main()
