"""26 — Strata: this machine's install history as a geological cross-section.

Every calendar day since the system was installed lays down one sediment bed,
read from /var/log/pacman.log (oldest at the bottom, today at the surface):
  * thickness ∝ log(1 + packages touched that day); quiet days leave a thin dust line
  * tint by what dominated the day: installs = sandstone, upgrades = shale,
    removals = a red oxide band
  * linux / mesa / hyprland upgrades leave a bright "ash bed" at the base of their day
  * big update days fault the rock: a dipping fault offsets every *older* bed,
    while the beds deposited afterwards lie undisturbed across it
  * older beds are folded more (fBm folding grows with depth)
The rock face is lit as relief (harder beds stand proud), and a field-log column
labels a few beds with their date, package count and notable upgrade.

Usage: python3 src/26-strata/strata.py [--scheme omarchy|all] [--scale 0.25]
"""
import collections
import datetime as dt
import hashlib
import math
import pathlib
import re
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from appfield import brand, write  # noqa: E402
from common import FONTS, H, W, box_blur, hex2arr, out_path, scheme_args, value_noise  # noqa: E402

SCHEMES = ["omarchy", "gruvbox", "everforest", "rose-pine"]
LOG = pathlib.Path("/var/log/pacman.log")
NOTABLE = ("linux", "mesa", "hyprland", "systemd", "glibc")
EVT = re.compile(r"^\[(\d{4}-\d\d-\d\d)T[^\]]*\] \[ALPM\] (installed|upgraded|removed) (\S+) \(([^)]*)\)")


def read_days():
    days = collections.defaultdict(lambda: {"installed": 0, "upgraded": 0, "removed": 0, "notable": []})
    for line in LOG.read_text(errors="replace").splitlines():
        m = EVT.match(line)
        if not m:
            continue
        day, kind, pkg, ver = m.groups()
        days[day][kind] += 1
        if kind == "upgraded" and pkg in NOTABLE:
            days[day]["notable"].append(f"{pkg} {ver.split('-> ')[-1].split('.arch')[0].split('-')[0].split(':')[-1]}")
    first = dt.date.fromisoformat(min(days))
    last = max(dt.date.fromisoformat(max(days)), dt.date.today())
    out = []
    d = first
    while d <= last:
        rec = days.get(d.isoformat(), {"installed": 0, "upgraded": 0, "removed": 0, "notable": []})
        rec = dict(rec, date=d.isoformat(), n=rec["installed"] + rec["upgraded"] + rec["removed"])
        out.append(rec)
        d += dt.timedelta(days=1)
    return out


def render(name, pal, s):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    bg, fg = c["background"], c["foreground"]
    days = read_days()

    # bed thicknesses (4K px), scaled so the column fills the lower ~80% of the screen
    th = np.array([7.0 if d["n"] == 0 else 16 + 30 * math.log1p(d["n"]) for d in days])
    surface = H * 0.2
    th *= (H - surface + 60) / th.sum()
    top = np.cumsum(th)                       # z of each bed's top, z = 0 at the bottom of the screen (+60 overscan)

    def tint(d):
        if d["n"] == 0:
            return bg * 0.7 + fg * 0.12
        k = max(("installed", "upgraded", "removed"), key=lambda q: d[q])
        hue = {"installed": c["yellow"], "upgraded": c.get("cyan", c["blue"]), "removed": c["red"]}[k]
        base = bg * 0.45 + fg * 0.3
        return base * 0.6 + hue * 0.4
    cols = np.stack([tint(d) * rng.uniform(0.85, 1.12) for d in days]).astype(np.float32)
    hard = rng.uniform(0, 1, len(days)).astype(np.float32)
    hard[[i for i, d in enumerate(days) if d["n"] == 0]] = 0.2

    # pixel -> undeformed depth z, then fold (stronger with depth) and fault
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32) / s
    depth = np.clip(yy - surface, 0, None)
    fold = (value_noise(h, w, max(int(900 * s), 8), rng, octaves=3) - 0.5) * 2
    fold2 = (value_noise(h, w, max(int(300 * s), 4), rng, octaves=3) - 0.5) * 2
    amp = 30 + 0.12 * depth
    z = (H + 60 - yy) + amp * fold + 0.25 * amp * fold2     # z grows upward
    big = [i for i, d in enumerate(days) if d["n"] >= 75 and i > 0]
    gouge = np.zeros((h, w), np.float32)
    for i in big:                                          # faults cut only beds older than day i
        x0 = rng.uniform(0.12, 0.88) * W
        dip = math.radians(rng.uniform(58, 76)) * rng.choice([-1, 1])
        throw = rng.uniform(35, 80)
        side = (xx - x0 - (yy - surface) / math.tan(dip)) > 0
        older = z < top[i - 1]
        z = np.where(side & older, z - throw, z)
        dist = np.abs((xx - x0 - (yy - surface) / math.tan(dip)) * math.sin(abs(dip)))
        gouge = np.maximum(gouge, np.exp(-dist ** 2 / 8) * (z < top[i - 1]))
    bed = np.clip(np.searchsorted(top, z), 0, len(days) - 1)
    air = z > top[-1]

    # within-bed texture: laminations + grain, plus relief shading from bed hardness
    frac = (z - np.concatenate([[0], top])[bed]) / th[bed]
    grain = value_noise(h, w, max(int(6 * s), 2), rng, octaves=2)
    lam = 0.5 + 0.5 * np.sin(frac * th[bed] / 7 + fold2 * 3)
    rgb = cols[bed] * (0.82 + 0.1 * lam[..., None] + 0.16 * (grain[..., None] - 0.5))
    relief = hard[bed] * 6 + grain * 1.5 + 3 * np.exp(-((frac - 0.0) * th[bed]) ** 2 / 8)
    relief = box_blur(relief.astype(np.float32), max(int(2 * s), 1))
    gy, gx = np.gradient(relief)
    shade = np.clip(1 + (-gx * 0.5 - gy * 0.8) * 0.6, 0.55, 1.4)
    rgb *= shade[..., None]

    # ash beds: a bright accent seam at the base of notable-upgrade days
    for i, d in enumerate(days):
        if d["notable"]:
            base = top[i - 1] if i else 0
            seam = np.exp(-((z - base - 4) ** 2) / (2 * 3.0 ** 2))
            rgb = rgb * (1 - 0.85 * seam[..., None]) + c["accent"] * 0.85 * seam[..., None]
    # fault planes as thin dark gouge lines (only through the beds they cut)
    rgb *= 1 - 0.7 * gouge[..., None]

    # sky above the surface: plain background gradient with a faint horizon glow
    t = np.clip((yy - 0) / (surface + 200), 0, 1)[..., None]
    sky = bg * (1 - t) + (bg * 0.7 + c["accent"] * 0.08 + fg * 0.05) * t
    rgb = np.where(air[..., None], sky, rgb)

    # field log: label a handful of beds on the right
    font = str(FONTS / "SpaceMono" / "SpaceMonoNerdFontMono-Regular.ttf")
    dim = pal.get("dark_foreground", pal["foreground"])
    pick = sorted(range(len(days)), key=lambda i: -days[i]["n"])[:6] + [0, len(days) - 1]
    xl = int(W * 0.86 * s)
    post = []
    for i in sorted(set(pick)):
        col = z[:, xl]
        rows = np.where((col > (top[i - 1] if i else 0)) & (col < top[i]))[0]
        if len(rows) == 0:
            continue
        y = int(rows.mean())
        d = days[i]
        note = (" · " + d["notable"][0]) if d["notable"] else ""
        label = f"{d['date']}  ·  {d['n']} pkgs{note}" if d["n"] else f"{d['date']}  ·  quiet"
        post += ["-stroke", pal["foreground"], "-strokewidth", str(max(s * 2, 1)), "-draw",
                 f"line {xl - int(120 * s)},{y} {xl - int(12 * s)},{y}", "-stroke", "none",
                 "-font", font, "-pointsize", str(max(int(22 * s), 6)), "-fill", pal["foreground"],
                 "-undercolor", pal["background"] + "c0",
                 "-gravity", "northwest", "-annotate", f"+{xl}+{y - int(14 * s)}", label, "+undercolor"]
    n_pk = sum(d["n"] for d in days)
    post += brand(pal, s, f"STRATA  ·  {len(days)} DAYS  ·  {n_pk} PACKAGE EVENTS  ·  {name.upper()}",
                  corner="northwest")
    write(np.clip(rgb, 0, 1), out_path("26-strata", f"strata--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
