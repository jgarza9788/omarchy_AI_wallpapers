"""11 — App Galaxy: a 3D spiral galaxy whose stars are Nerd Font app icons.

~3000 icons are placed in 3D: a spherical bulge of core-system glyphs (Arch,
Linux, Hyprland, terminal) and log-spiral arms of apps and dev tools, with a
thin, gaussian disc thickness. A perspective camera projects them, and icon size,
brightness and blur follow depth. Under the disc, a spacetime grid sags into a
gravity well (z ∝ -1/√(r²+a²)), showing the galaxy's weight. The core is the
Omarchy mark, glowing. The wordmark signs the corner.

Each colour scheme also gets its own galaxy (arm count, winding, camera angle),
seeded from the theme name.

Usage: python3 src/11-app-galaxy/app_galaxy.py [--scheme tokyo-night|all] [--scale 0.25]
"""
import hashlib
import math
import pathlib
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import (BRAND, FONTS, H, ROOT, W, box_blur, hex2arr, load_alpha,  # noqa: E402
                    out_path, ramp, save_rgb, scheme_args)

SCHEMES = ["tokyo-night", "osaka-jade", "retro-82", "hackerman", "ethereal"]
FONT = FONTS / "Iosevka" / "IosevkaNerdFontMono-Regular.ttf"

CORE = [0xF303, 0xF17C, 0xF359, 0xF489, 0xF120, 0xF08C7]                 # arch, linux, hypr, term
APPS = [0xF269, 0xF268, 0xE7C5, 0xF338, 0xE795, 0xF308, 0xE73C, 0xE739, 0xE791, 0xF1BC,
        0xF167, 0xE60B, 0xF0E0, 0xF1C0, 0xE706, 0xE7B1, 0xF07B, 0xF015, 0xF001, 0xF03D,
        0xF030, 0xF11B, 0xF1FC, 0xF0AD, 0xF121, 0xF126, 0xF09B, 0xF113, 0xF0AB0, 0xF0B79,
        0xF07B7, 0xF0A1E, 0xF0517, 0xF2DC, 0xF0C2, 0xF1B2, 0xF1EB, 0xE702, 0xF418, 0xE62B,
        0xE7A8, 0xE627, 0xE74E, 0xE620, 0xE718, 0xF013, 0xF233, 0xE615, 0xE61D, 0xE737, 0xF0219]
BUCKETS = np.geomspace(10, 110, 14)  # glyph pixel sizes at 4K


class Atlas:
    """Lazily rendered glyph alpha masks per (codepoint, pixel size)."""

    def __init__(self, cache):
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)
        self.mem = {}

    def get(self, cp, px):
        key = (cp, px)
        if key not in self.mem:
            f = self.cache / f"{cp:x}_{px}.gray"
            size = px + 4
            if not f.exists():
                raw = subprocess.run(
                    ["magick", "-size", f"{size}x{size}", "xc:black", "-font", str(FONT),
                     "-pointsize", str(px), "-fill", "white", "-gravity", "center",
                     "-annotate", "+0+0", chr(cp), "-depth", "8", "gray:-"],
                    check=True, capture_output=True).stdout
                f.write_bytes(raw)
            self.mem[key] = np.frombuffer(f.read_bytes(), np.uint8).reshape(size, size).astype(np.float32) / 255
        return self.mem[key]


def galaxy_points(rng, arms, winding, n=3000):
    """3D star positions (galaxy units, disc in the x-y plane) + kind (0 core, 1 arm, 2 halo)."""
    nb = int(n * 0.18)
    # bulge: compact spheroid
    v = rng.normal(0, 1, (nb, 3))
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    rb = rng.exponential(0.12, nb)
    bulge = v * rb[:, None] * np.array([1, 1, 0.6])
    nb = nb // 2
    bulge = bulge[:nb]
    # arms: log spirals with scatter that grows outward
    na = int(n * 0.72)
    r = 0.12 + rng.exponential(0.32, na)
    r = r[r < 1.25][:na]
    arm = rng.integers(0, arms, r.size)
    theta = arm * 2 * np.pi / arms + winding * np.log(r / 0.12) + rng.normal(0, 0.22 + 0.1 * r, r.size)
    z = rng.normal(0, 0.025 + 0.02 * np.exp(-r * 3), r.size)
    disc = np.stack([r * np.cos(theta), r * np.sin(theta), z], 1)
    # halo: sparse, wide
    nh = n - nb - r.size
    rh = rng.uniform(0.2, 1.5, nh)
    th = rng.uniform(0, 2 * np.pi, nh)
    halo = np.stack([rh * np.cos(th), rh * np.sin(th), rng.normal(0, 0.12, nh)], 1)
    pts = np.concatenate([bulge, disc, halo])
    kind = np.concatenate([np.zeros(nb, int), np.ones(r.size, int), np.full(nh, 2)])
    return pts, kind


class Camera:
    def __init__(self, elev_deg, azim_deg, dist, w, h, fov_deg=38):
        e, a = math.radians(elev_deg), math.radians(azim_deg)
        self.pos = np.array([dist * math.cos(e) * math.cos(a), dist * math.cos(e) * math.sin(a), dist * math.sin(e)])
        fwd = -self.pos / np.linalg.norm(self.pos)
        right = np.cross(fwd, [0, 0, 1])
        right /= np.linalg.norm(right)
        up = np.cross(right, fwd)
        self.R = np.stack([right, up, fwd])
        self.f = (w / 2) / math.tan(math.radians(fov_deg) / 2)
        self.cx, self.cy = w / 2, h / 2

    def project(self, p):
        c = (p - self.pos) @ self.R.T
        depth = c[..., 2]
        x = self.cx + self.f * c[..., 0] / depth
        y = self.cy - self.f * c[..., 1] / depth
        return x, y, depth


def splat(acc, xs, ys, color, weight):
    h, w, _ = acc.shape
    x0, y0 = np.floor(xs).astype(int), np.floor(ys).astype(int)
    fx, fy = xs - x0, ys - y0
    for dx, dy, wt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = x0 + dx, y0 + dy
        ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
        np.add.at(acc, (yi[ok], xi[ok]), color[ok] * (weight * wt)[ok, None])


def render(name, pal, s):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    arms = int(rng.choice([2, 2, 3, 4]))
    winding = rng.uniform(2.4, 3.6) * rng.choice([-1, 1])
    cam = Camera(rng.uniform(17, 26), rng.uniform(0, 360), 4.6, w, h)

    c = {k: hex2arr(v) for k, v in pal.items() if isinstance(v, str) and v.startswith("#")}
    bg = c["background"]
    dark = c.get("darker_background", bg)
    acc = np.zeros((h, w, 3), np.float32)
    grid = np.zeros((h, w, 3), np.float32)

    # --- spacetime grid with a gravity well, below the disc -------------------
    grid_col = c.get("muted", c["blue"]) * 0.6 + c["accent"] * 0.4
    L, step = 3.4, 0.16
    t = np.linspace(-L, L, int(5200 * max(s, 0.3)))
    for g in np.arange(-L, L + 1e-6, step):
        for xs3, ys3 in ((np.full_like(t, g), t), (t, np.full_like(t, g))):
            r2 = xs3 ** 2 + ys3 ** 2
            zs3 = -0.30 - 1.15 / np.sqrt(r2 / 0.06 + 1)        # the well
            px, py, d = cam.project(np.stack([xs3, ys3, zs3], 1))
            fade = np.clip(1 - np.sqrt(r2) / L, 0, 1) ** 0.8 * np.clip(5.5 / d, 0, 1.6)
            ok = d > 0.2
            splat(grid, px[ok], py[ok], np.broadcast_to(grid_col, (ok.sum(), 3)), 1.3 * fade[ok] / max(s, 0.25) ** 0.6)

    # --- dust / gas: faint points following the arms, blurred into nebulae ------
    dust, _ = galaxy_points(rng, arms, winding, n=60000)
    px, py, d = cam.project(dust)
    gas = np.zeros((h, w, 3), np.float32)
    rr = np.linalg.norm(dust[:, :2], axis=1)
    gas_col = ramp([c["yellow"], c.get("orange", c["red"]), c["magenta"], c["blue"]], np.clip(rr / 1.1, 0, 1))
    splat(gas, px, py, gas_col, np.full(px.size, 0.6, np.float32))
    gas = np.stack([box_blur(gas[..., i], 28 * s) for i in range(3)], -1)
    acc += gas * 1.4

    # --- icon stars, painted far -> near ---------------------------------------
    pts, kind = galaxy_points(rng, arms, winding, n=int(3200 * min(1, 0.4 + s)))
    px, py, d = cam.project(pts)
    order = np.argsort(-d)
    rr = np.linalg.norm(pts[:, :2], axis=1)
    star_col = ramp([c.get("bright_foreground", c["foreground"]), c["yellow"], c["accent"], c["cyan"],
                     c["blue"], c["magenta"]], np.clip(rr / 1.2, 0, 1))
    atlas = Atlas(ROOT / ".wip" / "atlas11")
    stars = np.zeros((h, w, 3), np.float32)
    for i in order:
        size_world = 0.055 if kind[i] == 0 else (0.04 if kind[i] == 1 else 0.03)
        size_world *= rng.uniform(0.6, 1.4)
        px_size = cam.f * size_world / d[i]          # cam.f is already in output pixels
        if px_size < 4 * s or not (-60 < px[i] < w + 60 and -60 < py[i] < h + 60):
            continue
        sizes = np.unique(np.maximum((BUCKETS * s).astype(int), 5))
        bucket = int(sizes[np.argmin(np.abs(sizes - px_size))])
        cp = (CORE[rng.integers(len(CORE))] if kind[i] == 0 and rng.random() < 0.7
              else APPS[rng.integers(len(APPS))])
        m = atlas.get(cp, bucket)
        bright = np.clip(3.2 / d[i], 0.25, 1.4) * (1.0 if kind[i] < 2 else 0.5)
        x0, y0 = int(px[i] - m.shape[1] / 2), int(py[i] - m.shape[0] / 2)
        xa, ya = max(x0, 0), max(y0, 0)
        xb, yb = min(x0 + m.shape[1], w), min(y0 + m.shape[0], h)
        if xa >= xb or ya >= yb:
            continue
        mm = m[ya - y0:yb - y0, xa - x0:xb - x0][..., None] * bright
        sl = stars[ya:yb, xa:xb]
        stars[ya:yb, xa:xb] = sl * (1 - np.clip(mm, 0, 1)) + star_col[i] * mm

    glow = np.stack([box_blur(stars[..., i], 12 * s) for i in range(3)], -1)
    acc += stars + glow * 1.1
    # the grid lies *under* the disc: hide it behind gas and stars
    cover = (gas.mean(-1) * 1.4 + stars.max(-1) + glow.mean(-1) * 1.5)[..., None]
    acc += grid * np.exp(-cover * 4.0)

    # --- Omarchy mark as the galactic core ---------------------------------------
    cx, cy, cd = cam.project(np.array([[0.0, 0.0, 0.0]]))
    core_px = int(cam.f * 0.16 / cd[0])
    mark = load_alpha(BRAND / "omarchy-logo.png", core_px, core_px)
    core = np.zeros((h, w), np.float32)
    x0, y0 = int(cx[0] - core_px / 2), int(cy[0] - core_px / 2)
    core[y0:y0 + core_px, x0:x0 + core_px] = mark
    halo = box_blur(core, 80 * s)
    bloom = box_blur(core, 280 * s)
    hot = c.get("bright_foreground", c["foreground"])
    acc += hot * core[..., None] * 1.2 + c["accent"] * halo[..., None] * 3.0 + c["yellow"] * bloom[..., None] * 3.5

    # --- background + tone map -------------------------------------------------
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    base = bg * (1 - yy) + dark * yy
    m = int(5000 * s * s * 4)
    splat(acc, rng.uniform(0, w, m), rng.uniform(0, h, m), np.broadcast_to(c["foreground"], (m, 3)),
          rng.uniform(0.05, 0.45, m).astype(np.float32))
    img = base + (1 - np.exp(-acc * 1.25)) * (1 - base)

    # --- branding: wordmark signature + caption --------------------------------
    font = str(FONTS / "SpaceMono" / "SpaceMonoNerdFontMono-Regular.ttf")
    wm = BRAND / "omarchy-wordmark.png"
    mgn = int(110 * s)
    dim = pal.get("dark_foreground", pal["foreground"])
    post = ["(", str(wm), "-alpha", "extract", "-resize", f"{int(520 * s)}x", "-background", pal["accent"],
            "-alpha", "shape", "-channel", "A", "-evaluate", "multiply", "0.85", "+channel", ")",
            "-gravity", "southwest", "-geometry", f"+{mgn}+{mgn + int(44 * s)}", "-composite",
            "-font", font, "-pointsize", str(max(int(24 * s), 7)), "-fill", dim, "-kerning", str(max(int(6 * s), 1)),
            "-annotate", f"+{mgn}+{mgn}", f"APP GALAXY  ·  {arms} ARMS  ·  {name.upper()}"]
    save_rgb(img, out_path("11-app-galaxy", f"app-galaxy--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for n in names:
        render(n, pals[n], scale)
