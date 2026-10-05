"""38 — Gel: everything installed, run out on an agarose gel under UV light.

A photograph of an electrophoresis gel on a transilluminator. Lane 1 is a size
ladder (1 KB … 1 GB); every other lane is one package source from
src/inventory.py, loaded into its well, and every package is a band. As with
DNA, migration distance falls with the log of size, so the heavy packages stay
up near the wells and the tiny scripts run far down the gel; brightness grows
with mass, bands of similar size pile into bright doublets, and bands blur more
the further they travel. Lanes "smile" a little, the busiest lanes smear,
there are a few bubbles, a gloved thumbprint, and a lab label with the run
conditions.

Usage: python3 src/38-gel/gel.py [--scheme omarchy|all] [--scale 0.5]
"""
import datetime as dt
import hashlib
import math
import pathlib
import socket
import subprocess
import sys
from xml.sax.saxutils import escape

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import inventory  # noqa: E402
from appfield import brand, write  # noqa: E402
from common import H, ROOT, W, box_blur, hex2arr, out_path, scheme_args, value_noise  # noqa: E402

SCHEMES = ["omarchy", "gruvbox", "catppuccin", "osaka-jade"]
MONO = "Iosevka Nerd Font Mono"
DISPLAY = "SpaceMono Nerd Font Mono"
LOG_MIN, LOG_MAX = 2.0, 9.4                # band axis: 100 B (bottom) … 2.5 GB (wells)
LADDER = [(1e3, "1 KB"), (1e4, "10 KB"), (1e5, "100 KB"), (1e6, "1 MB"), (1e7, "10 MB"), (1e8, "100 MB"), (1e9, "1 GB")]
SHORT = {"ladder": "ladder", "aur": "AUR", "omarchy": "omarchy", "flatpak": "flatpak", "runtime": "runtimes", "appimage": "AppImage",
         "omarchy-plugin": "plugins", "hypr-plugin": "hyprpm", "local-bin": "~/bin"}
GEL = (300, 250, 3560, 1960)               # gel slab x0, y0, x1, y1 (full-size pixels)
WELL_Y, RUN_END = 330, 1880                # wells and the furthest a band can travel


def migrate(nbytes):
    """Distance down the gel (0 at the well, 1 at the end) for a fragment of this size."""
    lg = math.log10(max(nbytes, 10 ** LOG_MIN))
    return min(max((LOG_MAX - lg) / (LOG_MAX - LOG_MIN), 0.0), 1.0)


def lane_layout():
    inv = inventory.load()
    lanes = [("ladder", [(b, 6.0, label) for b, label in LADDER])]
    for src, (n, _) in inventory.summary(inv).items():
        items = [(i["bytes"], None, i["name"]) for i in inv if i["source"] == src]
        lanes.append((src, items))
    return inv, lanes


def render(name, pal, s):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    inv, lanes = lane_layout()
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)

    bg = hex2arr(pal["darker_background"] if isinstance(pal.get("darker_background"), str) else pal["background"])
    dye = hex2arr(pal["accent"])
    uv = hex2arr(pal.get("magenta", pal["accent"]) if isinstance(pal.get("magenta"), str) else pal["accent"])

    # the transilluminator: dark box, a violet glow through the glass, a faint grid on the glass
    gx0, gy0, gx1, gy1 = (v * s for v in GEL)
    box = np.exp(-(((xx / w - 0.5) / 0.55) ** 2 + ((yy / h - 0.5) / 0.6) ** 2))
    img = bg * (0.55 + 0.25 * box[..., None]) + uv * 0.05 * box[..., None]
    grid = ((np.abs((xx / (120 * s)) % 1 - 0.5) < 0.012) | (np.abs((yy / (120 * s)) % 1 - 0.5) < 0.012))
    img += uv * 0.02 * grid[..., None]

    # the gel slab: translucent, slightly lit from below, with a bevel at the edges
    inside = (xx >= gx0) & (xx < gx1) & (yy >= gy0) & (yy < gy1)
    edge_d = np.minimum.reduce([xx - gx0, gx1 - xx, yy - gy0, gy1 - yy])
    grain = value_noise(h, w, max(int(30 * s), 2), rng, octaves=3)
    gel = (0.10 + 0.05 * grain) * inside
    bevel = np.exp(-np.clip(edge_d, 0, None) / (10 * s)) * inside
    img += uv[None, None] * gel[..., None] * 0.9 + dye * 0.10 * bevel[..., None]
    img *= (1 - 0.25 * inside[..., None] * (1 - box[..., None]))

    # bands: one intensity field, built lane by lane
    n_l = len(lanes)
    pitch = (gx1 - gx0) / n_l
    lw = pitch * 0.68
    field = np.zeros((h, w), np.float32)
    ys = np.arange(h, dtype=np.float32)
    lane_x = []
    for li, (src, items) in enumerate(lanes):
        cx = gx0 + pitch * (li + 0.5)
        lane_x.append(cx)
        prof = np.zeros(h, np.float32)
        for nbytes, weight, _ in items:
            d = migrate(nbytes)
            y = (WELL_Y + (RUN_END - WELL_Y) * d) * s
            sig = (2.2 + 9 * d ** 1.4) * s                  # bands spread the further they run
            mass = weight if weight is not None else max((max(nbytes, 100) / 1e6) ** 0.42, 0.9)
            prof += mass * np.exp(-0.5 * ((ys - y) / sig) ** 2) / sig * 4 * s
        if src != "ladder":                                   # a smear from the well for busy lanes
            smear = np.clip((ys - WELL_Y * s) / ((RUN_END - WELL_Y) * s), 0, 1)
            prof += 0.006 * len(items) ** 0.7 * (1 - smear) ** 2 * (ys > WELL_Y * s)
        x0, x1 = int(cx - lw / 2), int(cx + lw / 2)
        for x in range(max(x0 - int(6 * s), 0), min(x1 + int(6 * s), w)):
            u = (x - cx) / (lw / 2)
            across = 1 / (1 + np.exp((abs(u) - 0.92) * 22))       # soft lane edges
            smile = 9 * s * u * u                                  # bands curve up at the lane edges
            wob = 1.5 * s * math.sin(x * 0.05 / max(s, 0.1) + li)
            field[:, x] += across * np.interp(ys + smile + wob, ys, prof)
    field *= inside
    # tone: fluorescence saturates; a wide glow for the bright bands
    norm = np.percentile(field[field > 0], 99.4) if np.any(field > 0) else 1
    tm = 1 - np.exp(-field / (norm * 0.45))
    glow = box_blur(tm, 14 * s) * 0.55 + box_blur(tm, 48 * s) * 0.35
    img += dye * (tm[..., None] * 0.95 + glow[..., None] * 0.6)
    hot = np.clip((tm - 0.82) / 0.18, 0, 1)
    img += (1 - dye) * 0.55 * hot[..., None] * dye.max()        # brightest cores burn toward white

    # wells: dark slots with a lit rim
    for cx in lane_x:
        wx0, wx1, wy0, wy1 = cx - lw / 2, cx + lw / 2, (WELL_Y - 34) * s, (WELL_Y - 8) * s
        slot = (xx > wx0) & (xx < wx1) & (yy > wy0) & (yy < wy1)
        rim = (xx > wx0 - 3 * s) & (xx < wx1 + 3 * s) & (yy > wy0 - 3 * s) & (yy < wy1 + 3 * s) & ~slot
        img = np.where(slot[..., None], img * 0.35, img)
        img += dye * 0.25 * rim[..., None]

    # bubbles trapped in the agarose
    for _ in range(14):
        bx, by = rng.uniform(gx0 + 40 * s, gx1 - 40 * s), rng.uniform(gy0 + 120 * s, gy1 - 40 * s)
        r = rng.uniform(4, 16) * s
        d = np.hypot(xx - bx, yy - by)
        ring = np.exp(-((d - r) / (1.2 * s + r * 0.12)) ** 2)
        spec = np.exp(-(np.hypot(xx - bx + r * 0.35, yy - by + r * 0.35) / (r * 0.25 + 0.5)) ** 2)
        img += (0.10 * ring + 0.35 * spec)[..., None] * np.array([1, 1, 1])
    # a gloved thumbprint, near the lower right of the gel
    tx, ty = gx1 - 420 * s, gy1 - 260 * s
    du, dv = (xx - tx) / (150 * s), (yy - ty) / (190 * s)
    rr = np.hypot(du, dv) + 0.08 * np.sin(np.arctan2(dv, du) * 3) + 0.05 * np.sin(du * 5 + dv * 3)
    ridges = (0.5 + 0.5 * np.sin(rr * 70)) * np.exp(-(rr / 0.95) ** 6)
    img += uv * 0.03 * (ridges * inside)[..., None]

    # labels: marker-pen lane names, ladder sizes, the lab tape
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">']
    fg, dim = pal["foreground"], pal.get("dark_foreground", pal["foreground"])

    def t(x, y, s_, size, fill, anchor="middle", family=MONO, weight="normal", rot=0, op=1.0, spacing=0):
        svg.append(f'<text x="{x:.0f}" y="{y:.0f}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
                   f'fill="{fill}" fill-opacity="{op}" text-anchor="{anchor}" letter-spacing="{spacing}" '
                   f'transform="rotate({rot} {x:.0f} {y:.0f})">{escape(s_)}</text>')

    for li, (src, items) in enumerate(lanes):
        cx = lane_x[li] / s
        lab = SHORT.get(src, src)
        t(cx, 214, lab, 28, fg, family=DISPLAY, weight="bold", rot=rng.uniform(-4, 4))
        t(cx, 244, "M" if src == "ladder" else f"n={len(items)}", 21, dim)
        if src == "ladder":
            for b, label in LADDER:
                y = WELL_Y + (RUN_END - WELL_Y) * migrate(b)
                t(GEL[0] - 24, y + 8, label, 22, fg, anchor="end", op=0.85)
                svg.append(f'<line x1="{GEL[0] - 14}" y1="{y:.0f}" x2="{GEL[0] - 2}" y2="{y:.0f}" stroke="{fg}" '
                           f'stroke-opacity="0.6" stroke-width="2"/>')
    total = inventory.human(sum(i["bytes"] for i in inv))
    host = socket.gethostname()
    lx, ly = 3330, 2010
    svg.append(f'<g transform="rotate(-2 {lx} {ly})"><rect x="{lx - 520}" y="{ly - 50}" width="680" height="104" '
               f'fill="#efe9d8" fill-opacity="0.92"/>')
    svg.append(f'<text x="{lx - 500}" y="{ly - 12}" font-family="{DISPLAY}" font-size="26" font-weight="bold" '
               f'fill="#2a2620">{escape(host)} · {len(inv)} samples · {total}</text>')
    svg.append(f'<text x="{lx - 500}" y="{ly + 26}" font-family="{MONO}" font-size="22" fill="#2a2620">'
               f'1% agarose · TAE · 120 V · 45 min · {dt.date.today():%Y-%m-%d}</text></g>')
    svg.append("</svg>")
    tmp = ROOT / ".wip" / f"gel--{name}.svg"
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_text("\n".join(svg))
    png = tmp.with_suffix(f".{s}.png")
    subprocess.run(["rsvg-convert", "-w", str(w), "-h", str(h), "-o", str(png), str(tmp)], check=True)
    post = [str(png), "-composite"] + brand(pal, s, f"GEL  ·  {len(inv)} PACKAGES  ·  {name.upper()}", corner="southwest")
    write(np.clip(img, 0, 1), out_path("38-gel", f"gel--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
