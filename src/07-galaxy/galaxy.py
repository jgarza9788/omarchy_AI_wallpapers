"""07 — Your System, as a Galaxy: the pacman dependency graph of *this* machine.

Every installed package is a star (size ~ installed size). Its distance from the
core is its dependency depth: base libraries like glibc form the bulge, and the
apps you chose sit out in the arms. Angles come from a force-directed layout of
the real dependency graph, twisted along a log-spiral and tilted into a disc.
Dependency edges are drawn as faint filaments curving through the core.

Each colour scheme lights up a different *constellation*: the full dependency
closure of one app you use (hyprland, blender, gimp, omarchy, libreoffice).

Usage: python3 src/07-galaxy/galaxy.py [--scheme tokyo-night|all] [--scale 0.25]
"""
import os
import pathlib
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import FONTS, H, W, box_blur, hex2arr, out_path, ramp, save_rgb, scheme_args  # noqa: E402

CONSTELLATIONS = {          # scheme -> app whose dependency closure is highlighted
    "tokyo-night": "hyprland",
    "catppuccin": "blender",
    "gruvbox": "gimp",
    "ethereal": "omarchy",
    "nord": "libreoffice-fresh",
}
SCHEMES = list(CONSTELLATIONS)
UNITS = {"B": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3}


# --- data ---------------------------------------------------------------------
def read_packages():
    out = subprocess.run(["pacman", "-Qi"], capture_output=True, text=True,
                         env=dict(os.environ, LC_ALL="C")).stdout
    pkgs = {}
    for block in out.strip().split("\n\n"):
        f, key = {}, None
        for line in block.splitlines():
            if line[:1] != " " and ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                f[key] = val.strip()
            elif key:
                f[key] += " " + line.strip()
        num, unit = f["Installed Size"].split()
        pkgs[f["Name"]] = {
            "size": float(num) * UNITS[unit],
            "deps": [] if f["Depends On"] == "None" else f["Depends On"].split(),
            "provides": [] if f["Provides"] == "None" else f["Provides"].split(),
            "explicit": f.get("Install Reason", "").startswith("Explicitly"),
        }
    return pkgs


def build_graph(pkgs):
    names = sorted(pkgs)
    index = {n: i for i, n in enumerate(names)}
    provider = dict(index)
    for n, p in pkgs.items():
        for prov in p["provides"]:
            provider.setdefault(re.split(r"[<>=]", prov)[0], index[n])
    edges = set()
    for n, p in pkgs.items():
        for d in p["deps"]:
            j = provider.get(re.split(r"[<>=]", d)[0])
            if j is not None and j != index[n]:
                edges.add((index[n], j))
    return names, np.array(sorted(edges))


def depth_levels(n, edges):
    """Longest dependency chain below each package (0 = depends on nothing)."""
    deps = [[] for _ in range(n)]
    for a, b in edges:
        deps[a].append(b)
    level, state = [0] * n, [0] * n  # 0 new, 1 visiting, 2 done

    def visit(u):
        stack = [(u, iter(deps[u]))]
        state[u] = 1
        while stack:
            v, it = stack[-1]
            for w in it:
                if state[w] == 0:
                    state[w] = 1
                    stack.append((w, iter(deps[w])))
                    break
                if state[w] == 2:
                    level[v] = max(level[v], level[w] + 1)
            else:
                state[v] = 2
                stack.pop()
                if stack:
                    level[stack[-1][0]] = max(level[stack[-1][0]], level[v] + 1)

    for u in range(n):
        if state[u] == 0:
            visit(u)
    return np.array(level, np.float32)


def closure(root, edges, n):
    deps = [[] for _ in range(n)]
    for a, b in edges:
        deps[a].append(b)
    seen, todo = {root}, [root]
    while todo:
        for w in deps[todo.pop()]:
            if w not in seen:
                seen.add(w)
                todo.append(w)
    mask = np.zeros(n, bool)
    mask[list(seen)] = True
    return mask


def force_angles(n, edges, rng, iters=220):
    """Fruchterman–Reingold layout; we only keep each node's angle around the centroid."""
    pos = rng.normal(0, 1, (n, 2)).astype(np.float32)
    k = 1.0 / np.sqrt(n)
    t = 0.3
    for _ in range(iters):
        delta = pos[:, None, :] - pos[None, :, :]
        dist = np.sqrt((delta ** 2).sum(-1)) + 1e-3
        disp = (delta * (k * k / dist ** 2)[..., None]).sum(1)
        e = pos[edges[:, 0]] - pos[edges[:, 1]]
        el = np.sqrt((e ** 2).sum(-1, keepdims=True)) + 1e-3
        f = e * el / k
        np.add.at(disp, edges[:, 0], -f)
        np.add.at(disp, edges[:, 1], f)
        dl = np.sqrt((disp ** 2).sum(-1, keepdims=True)) + 1e-6
        pos += disp / dl * np.minimum(dl, t)
        t *= 0.985
    c = pos - pos.mean(0)
    return np.arctan2(c[:, 1], c[:, 0])


# --- rendering ------------------------------------------------------------------
def splat(acc, xs, ys, color, weight):
    """Add weighted colour at integer pixel positions (bilinear)."""
    h, w, _ = acc.shape
    x0, y0 = np.floor(xs).astype(int), np.floor(ys).astype(int)
    fx, fy = xs - x0, ys - y0
    for dx, dy, wt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = x0 + dx, y0 + dy
        ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
        np.add.at(acc, (yi[ok], xi[ok]), (color[ok] if color.ndim == 2 else color) * (weight * wt)[ok, None])


def render(name, pal, s, data):
    names, edges, level, theta0, sizes, explicit = data
    n = len(names)
    rng = np.random.default_rng(3)
    w, h = int(W * s), int(H * s)
    root = names.index(CONSTELLATIONS[name])
    lit = closure(root, edges, n)

    # galaxy coordinates. Rank-normalise so the data fills a disc: depth rank -> radius
    # (foundational libs in the bulge), force-layout angle rank -> azimuth (graph
    # neighbours stay neighbours), then a density wave pulls stars into 2 log-spiral arms.
    lv = level / level.max()
    depth_rank = np.argsort(np.argsort(level + rng.uniform(0, 0.99, n))) / (n - 1)
    ang_rank = np.argsort(np.argsort(theta0)) / n * 2 * np.pi
    r = 0.04 + 0.96 * depth_rank ** 1.15
    pitch = 2.4
    phi = ang_rank - pitch * np.log(r)
    arm = np.round(phi / np.pi) * np.pi
    theta = ang_rank + (arm - phi) * 0.78 * np.clip(r * 3, 0, 1) + rng.normal(0, 0.07, n)
    r = r * 0.46 + rng.normal(0, 0.012, n)
    tilt, rot = 0.55, -0.3
    gx, gy = r * np.cos(theta), r * np.sin(theta) * tilt
    X = (gx * np.cos(rot) - gy * np.sin(rot)) * w * 0.8 + w / 2
    Y = (gx * np.sin(rot) + gy * np.cos(rot)) * w * 0.8 + h / 2

    acc = np.zeros((h, w, 3), np.float32)
    bg = hex2arr(pal["background"])
    star_ramp = [hex2arr(pal["yellow"]), hex2arr(pal.get("orange", pal["red"])), hex2arr(pal["foreground"]),
                 hex2arr(pal["cyan"]), hex2arr(pal["blue"])]
    col = ramp(star_ramp, lv)
    accent = hex2arr(pal["accent"])

    # filaments: quadratic beziers bowed toward the core; the lit constellation is
    # sampled densely (continuous light threads), the rest sparsely (faint dust lanes)
    cx, cy = w / 2, h / 2
    a_all, b_all = edges[:, 0], edges[:, 1]
    hot_all = lit[a_all] & lit[b_all]
    for hot, n_t, weight in ((False, int(260 * s) + 20, 0.03), (True, int(1400 * s) + 40, 0.07)):
        sel = hot_all == hot
        a, b = a_all[sel], b_all[sel]
        t = np.linspace(0, 1, n_t, dtype=np.float32)[:, None]
        mx, my = (X[a] + X[b]) / 2 * 0.7 + cx * 0.3, (Y[a] + Y[b]) / 2 * 0.7 + cy * 0.3
        bx = (1 - t) ** 2 * X[a] + 2 * (1 - t) * t * mx + t ** 2 * X[b]
        by = (1 - t) ** 2 * Y[a] + 2 * (1 - t) * t * my + t ** 2 * Y[b]
        ecol = np.broadcast_to(accent, (len(a), 3)) if hot else col[a] * 0.6 + col[b] * 0.4
        splat(acc, bx.ravel(), by.ravel(), np.tile(ecol, (n_t, 1)), np.full(bx.size, weight, np.float32))

    # stars: gaussian blobs (sum of jittered splats approximates the PSF)
    rad = (0.6 + 1.4 * np.log10(sizes / 1024 + 1)) * 2.2 * s * 4
    bright = np.where(lit, 1.6, 0.6) * np.where(explicit, 1.6, 1.0)
    for _ in range(24):
        jx, jy = rng.normal(0, 1, n) * rad * 0.5, rng.normal(0, 1, n) * rad * 0.5
        splat(acc, X + jx, Y + jy, np.where(lit[:, None], col * 0.5 + accent * 0.5, col), bright * 0.6)
    splat(acc, X, Y, np.ones((n, 3), np.float32), bright * 4.0)

    # nebula + core glow from star density
    dens = np.zeros((h, w), np.float32)
    on = (X >= 0) & (X < w) & (Y >= 0) & (Y < h)
    np.add.at(dens, (Y[on].astype(int), X[on].astype(int)), np.sqrt(sizes[on] / 1e6) + 0.3)
    neb = box_blur(dens, 50 * s)
    neb /= neb.max() + 1e-6
    neb_col = ramp([hex2arr(pal["blue"]), hex2arr(pal["magenta"]), hex2arr(pal.get("orange", pal["red"]))], neb ** 0.5)
    acc += neb_col * (neb ** 1.1)[..., None] * 0.45

    # dust: background stars
    m = int(4000 * s * s * 4)
    splat(acc, rng.uniform(0, w, m), rng.uniform(0, h, m), hex2arr(pal["foreground"]), rng.uniform(0.05, 0.6, m))

    img = bg + (1 - np.exp(-acc * 1.4)) * (1 - bg)

    # labels: the constellation's root + its biggest members, plus a legend
    font = str(FONTS / "Iosevka" / "IosevkaNerdFontMono-Regular.ttf")
    pt = max(int(24 * s), 7)
    fg_dim = pal.get("dark_foreground", pal["foreground"])
    draw = []
    members = np.nonzero(lit)[0]
    picks = [root] + [i for i in members[np.argsort(-sizes[members])] if i != root][:14]
    for i in picks:
        x, y = int(X[i] + 20 * s), int(Y[i] - 12 * s)
        fill = pal["accent"] if i == root else fg_dim
        size = pt * (1.7 if i == root else 1.0)
        draw += ["-fill", fill, "-pointsize", str(int(size)), "-annotate", f"+{x}+{y}", names[i]]
    margin = int(90 * s)
    legend = (f"  {n} packages · {len(edges)} dependencies · "
              f"\uf005 {names[root]}: {int(lit.sum())} stars")
    post = ["-font", font, "-gravity", "northwest", *draw,
            "-gravity", "southwest", "-fill", fg_dim, "-pointsize", str(int(pt * 1.2)),
            "-annotate", f"+{margin}+{margin}", legend]
    save_rgb(img, out_path("07-galaxy", f"galaxy--{name}", s), post)


def load_data():
    pkgs = read_packages()
    names, edges = build_graph(pkgs)
    n = len(names)
    rng = np.random.default_rng(11)
    level = depth_levels(n, edges)
    theta0 = force_angles(n, edges, rng)
    sizes = np.array([max(pkgs[k]["size"], 1024) for k in names], np.float32)
    explicit = np.array([pkgs[k]["explicit"] for k in names])
    print(f"{n} packages, {len(edges)} edges, max depth {int(level.max())}")
    return names, edges, level, theta0, sizes, explicit


if __name__ == "__main__":
    schemes, scale, pals = scheme_args(SCHEMES)
    data = load_data()
    for nm in schemes:
        render(nm, pals[nm], scale, data)
