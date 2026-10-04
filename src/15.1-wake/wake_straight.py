"""15.1 — Wake: an interceptor plows a dead-straight line through the app grid.

A 3D interceptor (rendered by ship.py in Blender) crosses the launcher grid
faster than the icons can react. Ahead of the nose nothing has moved yet. Behind
it, inside the Mach cone (half-angle mu, sin mu = 1/M), icons are shoved
sideways out of the flight line:
  * the plow: |d| -> |d| + C * exp(-|d| / 1.2C) opens a clean channel of
    half-width C + 0.2·age (widening behind the ship) and compresses the icons beside it (monotone, so none cross)
  * the shock front: the push switches on sharply at the cone edge, so icons
    pile up into a ridge along the two shock lines
  * drag: icons near the line are also dragged a little along the flight path
Displaced icons tumble with the push and smear from their home slot as motion
streaks. Two tight ion jets run straight back from the engines down the channel,
with faint speed lines and a glowing bow shock.

Usage: python3 src/15.1-wake/wake_straight.py [--scheme omarchy|all] [--scale 0.25]
       (renders the ship sprite with Blender first if .wip/ship/ship--<scheme>.png is missing)
"""
import hashlib
import json
import math
import pathlib
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from appfield import APPS, Atlas, Canvas, affine, brand, finish, quantize, splat, write  # noqa: E402
from common import H, ROOT, W, hex2arr, out_path, ramp, scheme_args  # noqa: E402

SCHEMES = ["omarchy", "tokyo-night", "catppuccin", "gruvbox"]
PITCH = 124
SHIP_LEN = 620                    # on-screen hull length at 4K
SHIP_UNITS = (5.5, 7.4)           # hull length, ortho frame width (Blender units, see ship.py)


def ship_sprite(name):
    png = ROOT / ".wip" / "ship" / f"ship--{name}.png"
    if not png.exists():
        subprocess.run(["blender", "-b", "-P", str(pathlib.Path(__file__).with_name("ship.py")), "--",
                        "--scheme", name, "--samples", "96", "--size", "1600", "--out", str(png)],
                       check=True, stdout=subprocess.DEVNULL)
    return png, json.loads(png.with_suffix(".json").read_text())


def load_ship(png, meta, width, deg):
    """Sprite scaled to `width` px, rotated by `deg` (clockwise), on a square canvas -> RGB, alpha, map."""
    D = int(width * 1.15) | 1
    raw = subprocess.run(["magick", str(png), "-filter", "Lanczos", "-resize", f"{width}x",
                          "-background", "none", "-rotate", f"{deg}", "-gravity", "center",
                          "-extent", f"{D}x{D}", "-depth", "8", "rgba:-"],
                         check=True, capture_output=True).stdout
    img = np.frombuffer(raw, np.uint8).reshape(D, D, 4).astype(np.float32) / 255
    sw, sh = meta["size"]
    k = width / sw
    r = math.radians(deg)
    R = np.array([[math.cos(r), -math.sin(r)], [math.sin(r), math.cos(r)]])

    def to_screen(p):   # sprite pixel -> offset from the sprite centre on screen
        return R @ ((np.asarray(p) - [sw / 2, sh / 2]) * k)
    return img[..., :3], img[..., 3], to_screen


def plow(p, nose, u, nrm, mu, C, ramp_len):
    """Displace points p (N,2): channel opening + shock ridge + drag. Returns new p, signed push."""
    rel = p - nose
    age = -(rel @ u)                                   # >0 behind the nose
    d = rel @ nrm
    ad = np.abs(d)
    half = 40 + np.tan(mu) * np.clip(age, 0, None)     # Mach cone half-width
    inside = 1 / (1 + np.exp(-(half - ad) / 18))       # sharp switch-on at the shock
    grow = 1 - np.exp(-np.clip(age, 0, None) / ramp_len)
    Cg = (C + 0.2 * np.clip(age, 0, None)) * grow           # the channel keeps widening behind the ship
    push = Cg * np.exp(-ad / (1.2 * np.maximum(Cg, 1))) * inside
    drag = 70 * grow * np.exp(-ad / 260) * inside
    side = np.sign(d + 1e-6)
    q = p + (push * side)[:, None] * nrm - drag[:, None] * u
    return q, push * side


def render(name, pal, s):
    seed = int(hashlib.sha256(("straight" + name).encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    hot = c.get("bright_foreground", c["foreground"])
    muted = c.get("dark_foreground", c["foreground"]) * 0.75 + c["background"] * 0.25
    acc = c["accent"]
    jet_ramp = [np.ones(3, np.float32), hot * 0.5 + acc * 0.5, acc, acc * 0.5 + c["blue"] * 0.5]

    # dead-straight flight line, climbing gently left -> right
    theta = math.radians(-rng.uniform(6, 11))
    u = np.array([math.cos(theta), math.sin(theta)])
    nrm = np.array([-u[1], u[0]])
    centre = np.array([W * rng.uniform(0.62, 0.68), H * rng.uniform(0.44, 0.5)])
    mach = 4.2
    mu = math.asin(1 / mach)

    png, meta = ship_sprite(name)
    width_px = SHIP_LEN * SHIP_UNITS[1] / SHIP_UNITS[0]
    sprite_rgb, sprite_a, to_screen = load_ship(png, meta, max(int(width_px * s), 8), math.degrees(theta))
    off = lambda p: to_screen(p) / s                                     # noqa: E731  (4K units)
    nose = centre + off(meta["nose"])
    engines = [centre + off(e) for e in meta["engines"]]
    tail = centre + off(meta["tail"])

    # the grid
    # hexagonal lattice: rows sqrt(3)/2 * PITCH apart, every other row shifted half a pitch
    gx = np.arange(0, W + PITCH, PITCH)
    gy = np.arange(PITCH / 2, H, PITCH * math.sqrt(3) / 2)
    X, Y = np.meshgrid(gx, gy)
    X = X + (np.arange(len(gy)) % 2)[:, None] * PITCH / 2
    p0 = np.stack([X, Y], -1).reshape(-1, 2).astype(np.float64)
    p1, push = plow(p0, nose, u, nrm, mu, C=230, ramp_len=220)
    moved = np.linalg.norm(p1 - p0, axis=1)

    atlas = Atlas()
    canvas = Canvas(w, h)
    light = np.zeros((h, w, 3), np.float32)
    icon_px = quantize(58 * s, s)
    glyphs = [APPS[i] for i in rng.integers(0, len(APPS), len(p0))]
    k = max(s, 0.3)

    # speed lines: thin streaks parallel to the flight, densest near the channel
    n_lines = 260
    lp = nose - u[None] * rng.uniform(200, 4500, (n_lines, 1)) + nrm[None] * rng.normal(0, 520, (n_lines, 1))
    lens = rng.uniform(150, 900, n_lines)
    for i in range(n_lines):
        t = rng.random(int(lens[i] * s * 1.5) + 2)
        pts = lp[i] - u[None] * (t[:, None] * lens[i])
        fade = np.sin(np.pi * t) * 0.025 / k ** 0.5
        splat(light, pts[:, 0] * s, pts[:, 1] * s, acc * 0.5 + hot * 0.5, fade.astype(np.float32))

    # bow shock: two glowing lines along the Mach cone, fading with age
    for side in (-1, 1):
        a = rng.exponential(700, int(60000 * k))
        a = a[a < 4000]
        dirn = -u * math.cos(mu) + side * nrm * math.sin(mu)
        pts = nose[None] + dirn[None] * a[:, None] + nrm[None] * rng.normal(0, 1, (a.size, 1)) * (6 + 0.01 * a)[:, None]
        splat(light, pts[:, 0] * s, pts[:, 1] * s, ramp([hot, acc, acc * 0.4], a / 3000),
              (np.exp(-a / 1200) * 0.12 / k ** 0.5).astype(np.float32))

    # ion jets: straight and tight, white-hot at the bells, cooling to accent; plus a faint contrail
    for e in engines:
        a = rng.exponential(1100, int(220000 * k))
        a = a[a < 5000]
        spread = 2.5 + 0.012 * a
        pts = e[None] - u[None] * a[:, None] + nrm[None] * rng.normal(0, 1, (a.size, 1)) * spread[:, None]
        splat(light, pts[:, 0] * s, pts[:, 1] * s, ramp(jet_ramp, (a / 3500) ** 0.6),
              (np.exp(-a / 1600) * 0.09 / k ** 0.5).astype(np.float32))
        splat(light, np.array([e[0] * s]), np.array([e[1] * s]), hot, np.array([40.0], np.float32))
    a = rng.uniform(0, 6000, int(150000 * k))
    pts = tail[None] - u[None] * a[:, None] + nrm[None] * rng.normal(0, 1, (a.size, 1)) * (30 + 0.03 * a)[:, None]
    splat(light, pts[:, 0] * s, pts[:, 1] * s, acc, (np.exp(-a / 3000) * 0.012 / k ** 0.5).astype(np.float32))

    # icons: still ones first, then displaced ones smeared from home, least moved first
    for i in np.argsort(moved):
        g = atlas.get(glyphs[i], icon_px)
        m = moved[i]
        if m < 3:
            canvas.stamp(g, p0[i, 0] * s, p0[i, 1] * s, muted, alpha=0.8)
            continue
        agitation = float(np.clip(m / 350, 0, 1))
        col = muted * (1 - agitation) + (acc * 0.6 + hot * 0.4) * agitation
        A = affine(angle=float(push[i]) * 0.006 + float(rng.normal(0, 0.25)) * agitation)
        n = int(np.clip(m / 16, 4, 18))
        f = np.linspace(0, 1, n) ** 0.6                  # bunched toward the head: it decelerates
        pts = (p0[i][None] + (p1[i] - p0[i])[None] * f[:, None]) * s
        canvas.trail(g, pts, col, alpha=0.75 + 0.25 * agitation, A=A, power=1.4 + m / 200)

    light += canvas.rgb
    # soft accent light spilled under the hull
    glow = centre[None] + rng.normal(0, 1, (int(40000 * k), 2)) * [SHIP_LEN * 0.3, SHIP_LEN * 0.12]
    splat(light, glow[:, 0] * s, glow[:, 1] * s, acc, np.float32(0.02 / k ** 0.5))

    img = finish(light, pal, s, bloom=1.1, exposure=1.2, vignette=0.4)

    # the ship, alpha-over after tone mapping so its own shading stays intact
    D = sprite_a.shape[0]
    x0, y0 = int(round(centre[0] * s - D / 2)), int(round(centre[1] * s - D / 2))
    xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + D, w), min(y0 + D, h)
    al = sprite_a[ya - y0:yb - y0, xa - x0:xb - x0, None]
    img[ya:yb, xa:xb] = img[ya:yb, xa:xb] * (1 - al) + sprite_rgb[ya - y0:yb - y0, xa - x0:xb - x0] * al

    post = brand(pal, s, f"WAKE  ·  {int((moved > 3).sum())} APPS DISPLACED  ·  MACH {mach:.1f}  ·  {name.upper()}")
    write(img, out_path("15.1-wake", f"wake-straight--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
