"""13 — Event Horizon: the app galaxy falling into a black hole.

An accretion disk of Nerd Font app icons and glowing gas orbits a black hole, seen
almost edge-on. Gravitational lensing uses the point-lens equation in screen space:
a source at angular offset b from the hole appears at
    θ± = (b ± √(b² + 4θE²)) / 2
with tangential stretch θ/β and radial squash 1/(1 + θE²/θ²). θE grows with how far
behind the hole the source is. So the far side of the disk is bent up over the
shadow and down beneath it as a thin ring of light, background stars are pushed
outward, and icons near the ring are smeared into arcs. Icons on the innermost
orbits are spaghettified as they spiral in, and the approaching side of the disk
is Doppler-brightened.

Inspired by the toplist trend of thin glowing lines and huge negative space.

Usage: python3 src/13-event-horizon/event_horizon.py [--scheme matte-black|all] [--scale 0.25]
"""
import hashlib
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from appfield import APPS, CORE, Atlas, Camera, Canvas, affine, brand, finish, quantize, splat, write  # noqa: E402
from common import H, W, hex2arr, out_path, ramp, scheme_args  # noqa: E402

SCHEMES = ["matte-black", "tokyo-night", "vantablack", "catppuccin"]
R_IN, R_OUT = 3.0, 13.0          # disk extent in units of the Schwarzschild radius
SHADOW = 2.6                     # photon-capture radius, same units


def lens(x, y, depth, bx, by, bdepth, theta_e, r_shadow):
    """Point-lens images for screen points. Returns list of (x, y, mag, tangential, radial, angle, visible)."""
    dx, dy = x - bx, y - by
    b = np.hypot(dx, dy) + 1e-6
    ang = np.arctan2(dy, dx)
    behind = np.clip((depth - bdepth) * 1.5, 0, 1)   # sources more than ~1 rs behind are fully lensed
    te = theta_e * np.sqrt(behind)
    out = []
    for sign in (1, -1):
        root = np.sqrt(b * b + 4 * te * te)
        th = (b + sign * root) / 2                      # signed image radius
        r = np.abs(th)
        tang = r / b                                    # tangential stretch
        rad = 1 / (1 + te * te / np.maximum(r * r, 1e-6))
        mag = tang * rad
        a = ang if sign > 0 else ang + np.pi
        vis = (r > r_shadow) | (behind == 0)
        if sign < 0:
            vis &= behind > 0                           # only sources behind form secondary images
        out.append((bx + r * np.cos(a), by + r * np.sin(a), mag, tang, rad, a, vis))
    return out


def render(name, pal, s):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    hot = c.get("bright_foreground", c["foreground"])
    gas_ramp = [hot, c["yellow"], c.get("orange", c["red"]), c["red"], c["magenta"]]
    mono = name in ("vantablack",)
    if mono:
        gas_ramp = [hot, hot * 0.85, hot * 0.6, hot * 0.4, hot * 0.25]

    cam = Camera(elev_deg=rng.uniform(6, 11), azim_deg=-90, dist=48, w=w, h=h, fov_deg=30,
                 target=(rng.uniform(-3.5, -2.5), 0, 0))           # aim left of the hole -> hole sits right of centre
    bx, by, bd = cam.project(np.array([0.0, 0.0, 0.0]))
    px_per_unit = cam.f / bd
    r_shadow = SHADOW * px_per_unit
    theta_e = 4.2 * px_per_unit
    spin = 1.0  # disk rotates counter-clockwise seen from above

    light = np.zeros((h, w, 3), np.float32)

    # background stars, lensed (primary images only, pushed out of the shadow)
    n = int(9000 * s * s * 4 + 2000)
    sx, sy = rng.uniform(0, w, n), rng.uniform(0, h, n)
    imgs = lens(sx, sy, np.full(n, 1e6), bx, by, bd, theta_e * 1.3, r_shadow)
    x1, y1, mag, *_rest, vis = imgs[0]
    splat(light, x1[vis], y1[vis], c["foreground"], (rng.uniform(0.04, 0.5, n) * np.clip(mag, 0, 4))[vis])

    # accretion gas: dense particles, Keplerian Doppler, lensed into the ring
    m = int(260000 * max(s, 0.3))
    # thin ringlets (the 'glowing lines' look): radii cluster on ~60 rings
    rings = R_IN + (R_OUT - R_IN) * np.sort(rng.random(60)) ** 1.6
    r = rings[rng.integers(0, rings.size, m)] + rng.normal(0, 0.025, m)
    r = np.where(rng.random(m) < 0.3, R_IN + (R_OUT - R_IN) * rng.random(m) ** 1.8, r)
    phi = rng.uniform(0, 2 * np.pi, m)
    z = rng.normal(0, 0.05 + 0.02 * r, m)
    P = np.stack([r * np.cos(phi), r * np.sin(phi), z], 1)
    V = np.stack([-np.sin(phi), np.cos(phi), np.zeros(m)], 1) * spin / np.sqrt(r)[:, None]
    gx, gy, gd = cam.project(P)
    los = (P - cam.pos) / np.linalg.norm(P - cam.pos, axis=1, keepdims=True)
    approach = -(V * los).sum(1) * 2.2                     # >0 moving toward the camera
    doppler = np.clip(1 + approach, 0.35, 2.0) ** 1.5
    temp = np.clip((r - R_IN) / (R_OUT - R_IN), 0, 1) ** 0.6
    gcol = ramp(gas_ramp, temp)
    if not mono:
        gcol = gcol * (1 - 0.25 * np.clip(approach, 0, 1))[:, None] + c["accent"] * (0.25 * np.clip(approach, 0, 1))[:, None]
    weight = (0.12 + 0.6 * (1 - temp) ** 2) * doppler * (2.0 / max(s, 0.3)) ** 0.5
    front_light = np.zeros_like(light)       # near side of the disk passes in front of the hole
    front = gd < bd
    for gx2, gy2, mag, tang, rad, a, vis in lens(gx, gy, gd, bx, by, bd, theta_e, r_shadow):
        wgt = weight * np.clip(mag, 0, 6)
        splat(light, gx2[vis & ~front], gy2[vis & ~front], gcol[vis & ~front], wgt[vis & ~front])
        splat(front_light, gx2[vis & front], gy2[vis & front], gcol[vis & front], wgt[vis & front])

    # photon ring
    t = np.linspace(0, 2 * np.pi, int(30000 * max(s, 0.3)))
    rr = r_shadow * 1.04
    splat(light, bx + rr * np.cos(t), by + rr * np.sin(t), gas_ramp[1], np.full(t.size, 0.15))

    # icons in the disk, painted far -> near, with lens warps and spaghettification
    atlas = Atlas()
    canvas = Canvas(w, h)
    k = int(480 * min(1, 0.5 + s))
    ri = R_IN * 0.85 + (R_OUT - R_IN * 0.85) * rng.random(k) ** 1.2
    pi = rng.uniform(0, 2 * np.pi, k)
    Pi = np.stack([ri * np.cos(pi), ri * np.sin(pi), rng.normal(0, 0.06, k)], 1)
    ix, iy, idp = cam.project(Pi)
    lensed = lens(ix, iy, idp, bx, by, bd, theta_e, r_shadow)
    Vi = np.stack([-np.sin(pi), np.cos(pi), np.zeros(k)], 1) / np.sqrt(ri)[:, None]
    losi = (Pi - cam.pos) / np.linalg.norm(Pi - cam.pos, axis=1, keepdims=True)
    appr_i = -(Vi * losi).sum(1) * 2.2
    order = np.argsort(-idp)
    for i in order:
        cp = CORE[rng.integers(len(CORE))] if rng.random() < 0.15 else APPS[rng.integers(len(APPS))]
        base_px = 0.32 * px_per_unit * rng.uniform(0.6, 1.3)
        temp_i = np.clip((ri[i] - R_IN) / (R_OUT - R_IN), 0, 1)
        col = ramp(gas_ramp, np.array([temp_i]))[0] * 0.5 + hot * 0.5
        bright = float(np.clip(1 + appr_i[i], 0.3, 2.2)) * 0.9
        spag = float(np.clip((R_IN * 1.25 - ri[i]) / (R_IN * 0.5), 0, 1))   # inner icons are being torn apart
        for img_i, (lx, ly, mag, tang, rad, a, vis) in enumerate(lensed):
            if not vis[i]:
                continue
            if img_i == 1 and mag[i] < 0.08:
                continue
            px = quantize(base_px, s)
            if px < 5:
                continue
            g = atlas.get(cp, px)
            # lens: stretch tangentially (perpendicular to the radius), squash radially
            st = float(np.clip(tang[i], 1, 2.6))
            sq = float(np.clip(rad[i], 0.35, 1))
            A = affine(angle=0.0, stretch=st, squash=sq, axis=float(a[i]) + math.pi / 2)
            if spag:
                A = affine(stretch=1 + 1.8 * spag, squash=1 - 0.45 * spag, axis=float(a[i])) @ A
            canvas.stamp(g, lx[i], ly[i], col, alpha=min(1.0, bright * float(np.sqrt(mag[i]))), A=A)

    light += canvas.rgb * 1.6
    # the shadow: nothing escapes
    yy, xx = np.mgrid[0:h, 0:w]
    hole = np.hypot(xx - bx, yy - by) < r_shadow
    near_side = canvas.a > 0.05
    light[hole & ~near_side] = 0
    light += front_light

    img = finish(light, pal, s, bloom=1.3, exposure=1.1, vignette=0.5)
    post = brand(pal, s, f"EVENT HORIZON  ·  θE {theta_e / px_per_unit:.1f} rs  ·  {name.upper()}")
    write(img, out_path("13-event-horizon", f"event-horizon--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
