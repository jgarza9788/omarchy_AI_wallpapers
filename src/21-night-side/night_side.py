"""21 — Night Side: a dark planet's limb, with one city that spells OMA.

Riffs on the glowing-planet-limb wallpapers on Wallhaven's minimalism toplist.
A huge sphere fills the bottom of the frame, lit from behind, so only a thin
crescent of dawn shows on the limb under a thin, sun-tinted atmosphere. The night
side is covered in city lights: an equirectangular map of continents (fBm
noise), clustered city points and road-like threads between them, sampled onto
the sphere so everything foreshortens toward the horizon. One cluster is laid
out along the exact OMA logo outline: an easter egg, not a headline.

Usage: python3 src/21-night-side/night_side.py [--scheme tokyo-night|all] [--scale 0.25]
"""
import hashlib
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import oma_shapes  # noqa: E402
from appfield import splat  # noqa: E402
from common import FONTS, H, W, box_blur, hex2arr, out_path, save_rgb, scheme_args, smoothstep, value_noise  # noqa: E402

SCHEMES = ["tokyo-night", "nord", "osaka-jade", "ethereal"]
MW, MH = 4096, 2048        # equirectangular city-light map


def light_map(rng, oma_lon, oma_lat):
    """Continents + city lights (equirectangular, lon -180..180 -> x, lat 90..-90 -> y)."""
    land = value_noise(MH, MW, 700, rng, octaves=6, persistence=0.5)
    land = smoothstep(0.5, 0.56, land)
    lights = np.zeros((MH, MW, 3), np.float32)
    # cities cluster near coasts: sample candidate points, keep those on land near the edge
    coast = np.clip(box_blur(land, 12) * (1 - box_blur(land, 12)) * 4, 0, 1)
    n = 200000
    px, py = rng.uniform(0, MW, n), rng.uniform(MH * 0.1, MH * 0.9, n)
    keep = rng.random(n) < (land[py.astype(int), px.astype(int)] * (0.15 + 0.85 * coast[py.astype(int), px.astype(int)]))
    px, py = px[keep], py[keep]
    sizes = rng.pareto(1.6, px.size) + 1
    for k in range(5):     # each city is a little cluster of points
        j = rng.normal(0, 1.5, (px.size, 2)) * np.sqrt(sizes)[:, None]
        splat(lights, px + j[:, 0], py + j[:, 1], np.array([1.0, 1.0, 1.0]), (0.35 * sizes).astype(np.float32))
    # the OMA cluster: lights along the three logo outlines
    for key in "OMA":
        pts = np.array(oma_shapes.normalized(oma_shapes.PIECES[key](), 1.0))
        closed = np.vstack([pts, pts[:1]])
        seg = np.hypot(*np.diff(closed, axis=0).T)
        t = np.concatenate([[0], np.cumsum(seg)])
        u = np.linspace(0, t[-1], int(t[-1] * 260))          # uniform spacing along the outline
        dense = np.stack([np.interp(u, t, closed[:, 0]), np.interp(u, t, closed[:, 1])], 1)
        off = {"O": -1.15, "M": 0.0, "A": 1.15}[key]
        lon = oma_lon + (dense[:, 0] + off) * 1.6   # screen x runs toward +lon
        lat = oma_lat - dense[:, 1] * 1.6           # screen up runs toward lower lat (we face the pole)
        x = (lon + 180) / 360 * MW
        y = (90 - lat) / 180 * MH
        splat(lights, x + rng.normal(0, 0.6, x.size), y + rng.normal(0, 0.6, x.size), np.array([1.0, 1.0, 1.0]),
              np.full(x.size, 0.55, np.float32))
    return land, lights


def render(name, pal, s):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    warm = c["yellow"] * 0.6 + c.get("orange", c["red"]) * 0.4
    atmo = c["accent"] * 0.5 + c["blue"] * 0.5

    R = 1.55 * w
    cx, cy = w * 0.5, h + R * 0.86            # only the top cap is on screen
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = (xx - cx) / R, (yy - cy) / R
    r2 = dx * dx + dy * dy
    inside = r2 < 1
    nz = np.sqrt(np.clip(1 - r2, 0, 1))
    # tilt the globe toward the viewer so we see the top of the night side
    tilt = math.radians(58)
    ny = dy * math.cos(tilt) - nz * math.sin(tilt)
    nz2 = dy * math.sin(tilt) + nz * math.cos(tilt)
    lat = np.degrees(np.arcsin(np.clip(-ny, -1, 1)))
    lon = np.degrees(np.arctan2(dx, -nz2))        # visible cap faces lon 0, so the ±180 seam is on the far side
    sun = np.array([-0.55, -0.45, -0.70])
    sun /= np.linalg.norm(sun)
    ndots = dx * sun[0] + dy * sun[1] + nz * sun[2]

    oma_lat = float(np.median(lat[inside & (yy > h * 0.78) & (np.abs(xx - w * 0.62) < 20 * s)])) if inside.any() else 0
    oma_lon = float(np.median(lon[inside & (yy > h * 0.78) & (np.abs(xx - w * 0.62) < 20 * s)])) if inside.any() else 0
    land, lights = light_map(rng, oma_lon, oma_lat)
    mx = np.clip(((lon + 180) / 360 * MW).astype(int), 0, MW - 1)
    my = np.clip(((90 - lat) / 180 * MH).astype(int), 0, MH - 1)
    city = lights[my, mx]
    landv = land[my, mx]

    img = np.zeros((h, w, 3), np.float32)
    # night side: city lights, dimmed toward the limb (foreshortening + atmosphere)
    night = smoothstep(0.1, -0.15, ndots) * inside
    limb_fade = np.clip(nz * 3, 0, 1)
    img += city * (warm * 1.2 + 0.25)[None, None] * (night * limb_fade)[..., None] * 1.3
    # faint land/sea under the dawn crescent
    day = np.clip(ndots, 0, 1) * inside
    surf = (c["blue"] * 0.25 + c["background"] * 0.75) * (1 - landv[..., None]) + (c["green"] * 0.25 + c["background"] * 0.6) * landv[..., None]
    img += surf * day[..., None] * 0.8
    img += c["background"] * 0.25 * inside[..., None]
    # atmosphere: a thin shell outside the limb and a rim just inside it, brighter toward the sun
    rr = np.sqrt(r2)
    height = (rr - 1) * R / (60 * s * 4)
    sunward = np.clip(0.5 + 0.5 * (dx * sun[0] + dy * sun[1]) / (rr + 1e-6) * 1.6, 0, 1)
    shell = np.where(rr >= 1, np.exp(-np.clip(height, 0, None)), np.exp(-(1 - rr) * R / (14 * s * 4)))
    col_atmo = atmo * (1 - sunward[..., None] ** 2) + warm * sunward[..., None] ** 2
    img += col_atmo * (shell * (0.25 + 1.4 * sunward ** 3))[..., None]

    # stars above the limb
    n = int(6000 * s * s * 4)
    sx, sy = rng.uniform(0, w, n), rng.uniform(0, h, n)
    ok = ((sx - cx) ** 2 + (sy - cy) ** 2) > (R * 1.01) ** 2
    splat(img, sx[ok], sy[ok], c["foreground"], rng.uniform(0.05, 0.6, n)[ok].astype(np.float32))

    glow = np.stack([box_blur(img[..., i], 10 * s) for i in range(3)], -1)
    img = img + glow * 0.6
    bg = c.get("darker_background", c["background"])
    out = bg + (1 - np.exp(-img * 1.3)) * (1 - bg)

    font = str(FONTS / "SpaceMono" / "SpaceMonoNerdFontMono-Regular.ttf")
    dim = pal.get("dark_foreground", pal["foreground"])
    m = int(110 * s)
    post = ["-font", font, "-pointsize", str(max(int(24 * s), 7)), "-fill", dim, "-kerning", str(max(int(6 * s), 1)),
            "-gravity", "northwest", "-annotate", f"+{m}+{m}", f"OMARCHY  ·  NIGHT SIDE  ·  {name.upper()}"]
    save_rgb(out, out_path("21-night-side", f"night-side--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
