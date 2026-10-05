"""39 — Shell Metro: ~/.bash_history drawn as a metro map.

Every command you type most is a line (cd, ls, git, code, claude, sudo …),
its most frequent first arguments are the stations (git: add, status, clone …),
ordered outward from the hub by how often you go there, and line width is
ridership. All lines run through "~", the home interchange. Stations that share
a name on two lines (git add / hyprpm add) are interchanges, joined by a
walkway; pipes you use (history | fzf) are dashed express tunnels. A river,
/dev/null, runs through the middle, and a legend lists the lines and journeys.

Only short, plain tokens become station names: paths are cut to their last
part, and anything long, numbered, quoted or containing "=" is left out, so the
map never shows file names, URLs or values from the command line.

Usage: python3 src/39-shell-metro/shell_metro.py [--scheme omarchy|all] [--scale 0.5]
"""
import collections
import math
import pathlib
import re
import subprocess
import sys
from xml.sax.saxutils import escape

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from appfield import brand, write  # noqa: E402
from common import H, ROOT, W, hex2arr, out_path, scheme_args, value_noise  # noqa: E402

SCHEMES = ["omarchy", "tokyo-night", "flexoki-light", "kanagawa"]
HISTORY = pathlib.Path.home() / ".bash_history"
MONO = "Iosevka Nerd Font Mono"
DISPLAY = "SpaceMono Nerd Font Mono"
N_LINES, MAX_STATIONS = 10, 6
HUB = (1470, 1080)
STEP = 168
LINE_KEYS = ["red", "green", "yellow", "blue", "magenta", "cyan", "orange", "bright_red", "bright_cyan", "bright_magenta"]
TOKEN = re.compile(r"^[A-Za-z~.][A-Za-z0-9._~+-]{0,15}$")
SECRETISH = re.compile(r"(key|token|pass|secret|auth)", re.I)


def clean(tok):
    """A token as a station name, or None if it could carry anything private."""
    tok = tok.strip("'\"")
    if re.search(r"\.(png|jpe?g|webp|gif|mp4|mkv|pdf|zip|tar|gz)$", tok, re.I):     # files are not places
        return None
    if "=" in tok or SECRETISH.search(tok) or tok.startswith("-") and len(tok) > 6:
        return None
    if "/" in tok:
        parts = [p for p in tok.split("/") if p]
        tok = parts[-1] if parts else "/"
        if tok.startswith(".") and tok not in (".", ".."):
            tok = tok[1:]
        tok = re.sub(r"\.(png|jpe?g|webp|sh|py|txt|md)$", "", tok)
    if re.search(r"\d{4,}", tok) or not TOKEN.match(tok) or any(
            len(seg) >= 5 and re.search(r"\d", seg) and re.search(r"[a-z]", seg) for seg in re.split(r"[-_.]", tok)):
        return None
    return tok


def read_history():
    lines = HISTORY.read_text(errors="ignore").splitlines() if HISTORY.exists() else []
    count, subs, pipes = collections.Counter(), collections.defaultdict(collections.Counter), collections.Counter()
    for raw in lines:
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        segs = [s.split() for s in raw.split("|")]
        if not segs[0]:
            continue
        cmd = clean(segs[0][0].lstrip("./")) or segs[0][0].split("/")[-1][:16]
        count[cmd] += 1
        if len(segs[0]) > 1:
            st = clean(segs[0][1])
            if st:
                subs[cmd][st] += 1
        for a, b in zip(segs, segs[1:]):
            if a and b:
                ca, cb = clean(a[0]), clean(b[0])
                if ca and cb:
                    pipes[(ca, cb)] += 1
    return len(lines), count, subs, pipes


def layout(count, subs):
    """Lines run through the hub along octilinear axes; lines sharing an axis leave it as parallel tracks,
    then fan out (straight, +45°, -45°) after their first station. Spacing fills the room in each direction."""
    lines = [c for c, _ in count.most_common(N_LINES)]
    axes = [0, 90, 45, 135, 0, 45, 135, 0, 90, 45]
    fan = {0: 0, 1: 1, 2: -1}
    shared = collections.Counter(st for c in lines for st in subs[c])
    routes, per_axis = {}, collections.Counter()
    x_lo, x_hi, y_lo, y_hi = 160, 2780, 170, 1990

    def room(p, v):                                   # distance from p to the map edge along v
        ts = []
        for lo, hi, pc, vc in ((x_lo, x_hi, p[0], v[0]), (y_lo, y_hi, p[1], v[1])):
            if vc > 1e-6:
                ts.append((hi - pc) / vc)
            elif vc < -1e-6:
                ts.append((lo - pc) / vc)
        return min(ts) if ts else 1e9

    for i, c in enumerate(lines):
        ax = axes[i]
        k = per_axis[ax]
        per_axis[ax] += 1
        a = math.radians(ax)
        d = np.array([math.cos(a), math.sin(a)])
        nrm = np.array([-d[1], d[0]])
        off = (k - 1) * 46 if axes.count(ax) > 1 else 0
        sts = [st for st, n in subs[c].most_common(MAX_STATIONS) if n >= 2]
        arms = [sts[0::2], sts[1::2]]
        pts, stations = [], []
        for side, arm in ((1, arms[0]), (-1, arms[1])):
            p = np.array(HUB, float) + nrm * off
            path = [p.copy()]
            dirv = d * side
            first = 330
            p = p + dirv * first
            path.append(p.copy())
            if arm:
                stations.append((arm[0], p.copy(), dirv.copy()))
            turn = fan[k % 3] * side
            if turn:
                b = math.atan2(dirv[1], dirv[0]) + turn * math.pi / 4
                dirv = np.array([math.cos(b), math.sin(b)])
            rest = arm[1:]
            step = min(300, (room(p, dirv) - 120) / (len(rest) + 0.9)) if rest else 0
            for st in rest:
                p = p + dirv * step
                path.append(p.copy())
                stations.append((st, p.copy(), dirv.copy()))
            if arm:
                tail = p + dirv * max(min(step, 200) * 0.7, 120)
            else:                                     # a branch with no stops still runs out into the map
                tail = p + dirv * min(room(p, dirv) * 0.5, 620)
            path.append(tail)
            pts.append((side, path, tail, dirv))
        routes[c] = {"arms": pts, "stations": stations, "n": count[c]}
    return lines, routes, shared


def render(name, pal, s):
    total, count, subs, pipes = read_history()
    lines, routes, shared = layout(count, subs)
    w, h = int(W * s), int(H * s)
    rng = np.random.default_rng(39)
    light = pal.get("mode") == "light"
    bg = hex2arr(pal["background"])
    grain = value_noise(h, w, max(int(5 * s), 2), rng, octaves=2)
    img = bg * (0.97 + 0.05 * grain[..., None])

    fg, dim = pal["foreground"], pal.get("dark_foreground", pal["foreground"])
    paper = pal["background"]
    col = {c: (pal.get(LINE_KEYS[i]) if isinstance(pal.get(LINE_KEYS[i]), str) else pal["accent"]) for i, c in enumerate(lines)}
    top = max(r["n"] for r in routes.values())
    width = {c: 12 + 20 * (routes[c]["n"] / top) ** 0.5 for c in lines}
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">']

    def t(x, y, s_, size, fill, anchor="start", family=MONO, weight="normal", op=1.0, style="normal", spacing=0):
        o.append(f'<text x="{x:.0f}" y="{y:.0f}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
                 f'font-style="{style}" fill="{fill}" fill-opacity="{op}" text-anchor="{anchor}" '
                 f'letter-spacing="{spacing}">{escape(s_)}</text>')

    # the river /dev/null
    river = "M -50,1520 C 500,1380 900,1640 1400,1480 S 2300,1300 2700,1420 S 3400,1560 3900,1380"
    o.append(f'<path d="{river}" fill="none" stroke="{pal.get("blue", fg)}" stroke-opacity="{0.16 if not light else 0.22}" '
             f'stroke-width="120" stroke-linecap="round"/>')
    t(560, 1488, "River  /dev/null", 30, pal.get("blue", fg), style="italic", op=0.55, spacing=4)

    # lines: a casing then the colour, octilinear polylines with rounded joins
    def poly(path):
        return " ".join(f"{x:.0f},{y:.0f}" for x, y in path)
    for c in lines:
        for side, path, tail, dirv in routes[c]["arms"]:
            o.append(f'<polyline points="{poly(path)}" fill="none" stroke="{paper}" stroke-width="{width[c] + 10:.0f}" '
                     f'stroke-linejoin="round" stroke-linecap="round"/>')
    for c in lines:
        for side, path, tail, dirv in routes[c]["arms"]:
            o.append(f'<polyline points="{poly(path)}" fill="none" stroke="{col[c]}" stroke-width="{width[c]:.0f}" '
                     f'stroke-linejoin="round" stroke-linecap="butt"/>')

    # pipes: dashed express tunnels between stations or line termini that share the command name
    where = {}
    for c in lines:
        where.setdefault(c, routes[c]["arms"][0][2])
        for st, p, _ in routes[c]["stations"]:
            where.setdefault(st, p)
    express = [(a, b, n) for (a, b), n in pipes.most_common(8) if a in where and b in where and a != b]
    for a, b, n in express:
        (x0, y0), (x1, y1) = where[a], where[b]
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2 - 160
        o.append(f'<path d="M {x0:.0f},{y0:.0f} Q {mx:.0f},{my:.0f} {x1:.0f},{y1:.0f}" fill="none" stroke="{fg}" '
                 f'stroke-opacity="0.55" stroke-width="5" stroke-dasharray="18 12"/>')

    # stations: ticks, or interchange rings where a name is on several lines
    placed = []
    inter = collections.defaultdict(list)
    for c in lines:
        for st, p, dirv in routes[c]["stations"]:
            inter[st].append((c, p))
    for st, spots in inter.items():
        if len(spots) > 1:                                      # walkway between nearby interchange platforms
            for (c0, p0), (c1, p1) in zip(spots, spots[1:]):
                if np.hypot(*(p0 - p1)) > 520:
                    continue
                o.append(f'<line x1="{p0[0]:.0f}" y1="{p0[1]:.0f}" x2="{p1[0]:.0f}" y2="{p1[1]:.0f}" stroke="{fg}" '
                         f'stroke-width="12" stroke-opacity="0.85" stroke-dasharray="2 14" stroke-linecap="round"/>')
    for c in lines:
        for st, p, dirv in routes[c]["stations"]:
            nrm = np.array([-dirv[1], dirv[0]])
            if len(inter[st]) > 1:
                o.append(f'<circle cx="{p[0]:.0f}" cy="{p[1]:.0f}" r="{width[c] * 0.75 + 8:.0f}" fill="{paper}" '
                         f'stroke="{fg}" stroke-width="7"/>')
            else:
                a, b = p + nrm * (width[c] * 0.5 + 12), p
                o.append(f'<line x1="{a[0]:.0f}" y1="{a[1]:.0f}" x2="{b[0]:.0f}" y2="{b[1]:.0f}" stroke="{col[c]}" '
                         f'stroke-width="12"/>')
            for side in (1, -1, 1.8, -1.8):                   # flip to the other side if it would collide
                nn = nrm * side
                lp = p + nn * (width[c] * 0.5 + 30)
                anchor = "start" if nn[0] > 0.3 else "end" if nn[0] < -0.3 else "middle"
                dy = 12 if abs(nn[1]) < 0.3 else (40 if nn[1] > 0 else -10)
                bw = len(st) * 18 + 10
                bx = lp[0] - (0 if anchor == "start" else bw if anchor == "end" else bw / 2)
                box = (bx, lp[1] + dy - 28, bx + bw, lp[1] + dy + 6)
                if not any(box[0] < q[2] and q[0] < box[2] and box[1] < q[3] and q[1] < box[3] for q in placed) and \
                        np.hypot(lp[0] - HUB[0], lp[1] - HUB[1]) > 170:
                    break
            t(lp[0], lp[1] + dy, st, 30, fg, anchor=anchor, family=DISPLAY, weight="bold")
            placed.append(box)
    # termini: a roundel with the line name at each end
    for c in lines:
        for side, path, tail, dirv in routes[c]["arms"]:
            ww = 34 + 20 * len(c)
            o.append(f'<rect x="{tail[0] - ww / 2:.0f}" y="{tail[1] - 30:.0f}" width="{ww}" height="60" rx="30" '
                     f'fill="{col[c]}"/>')
            t(tail[0], tail[1] + 11, c, 32, paper, anchor="middle", family=DISPLAY, weight="bold")
    # the hub
    o.append(f'<circle cx="{HUB[0]}" cy="{HUB[1]}" r="130" fill="{paper}" stroke="{fg}" stroke-width="10"/>')
    t(HUB[0], HUB[1] + 36, "~", 120, fg, anchor="middle", family=DISPLAY, weight="bold")
    t(HUB[0], HUB[1] + 78, "HOME", 24, dim, anchor="middle", family=DISPLAY, weight="bold", spacing=8)

    # legend
    lx, ly = 2980, 230
    o.append(f'<rect x="{lx - 50}" y="{ly - 90}" width="830" height="{170 + 66 * len(lines) + 260}" rx="18" '
             f'fill="{paper}" fill-opacity="0.92" stroke="{dim}" stroke-width="3"/>')
    t(lx, ly, "SHELL METRO", 56, fg, family=DISPLAY, weight="bold", spacing=6)
    t(lx, ly + 48, f"~/.bash_history · {total:,} journeys · {len(lines)} lines", 26, dim)
    for i, c in enumerate(lines):
        y = ly + 120 + i * 66
        o.append(f'<rect x="{lx}" y="{y - 22}" width="90" height="{min(width[c], 30):.0f}" rx="6" fill="{col[c]}"/>')
        t(lx + 120, y, c, 32, fg, family=DISPLAY, weight="bold")
        t(lx + 730, y, f"{routes[c]['n']:,}", 30, dim, anchor="end")
    y = ly + 120 + len(lines) * 66 + 30
    o.append(f'<line x1="{lx}" y1="{y}" x2="{lx + 90}" y2="{y}" stroke="{fg}" stroke-width="5" stroke-dasharray="18 12"/>')
    t(lx + 120, y + 10, "express tunnel = a pipe", 26, fg)
    for j, ((a, b), n) in enumerate(pipes.most_common(3)):
        t(lx + 120, y + 52 + j * 36, f"{a} | {b}   ×{n}", 24, dim)
    y += 52 + 3 * 36 + 20
    o.append(f'<circle cx="{lx + 45}" cy="{y - 8}" r="20" fill="{paper}" stroke="{fg}" stroke-width="6"/>')
    ints = [st for st, sp in inter.items() if len(sp) > 1]
    t(lx + 120, y, "interchange: " + (", ".join(ints[:4]) if ints else "none"), 26, fg)
    o.append("</svg>")

    tmp = ROOT / ".wip" / f"metro--{name}.svg"
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_text("\n".join(o))
    png = tmp.with_suffix(f".{s}.png")
    subprocess.run(["rsvg-convert", "-w", str(w), "-h", str(h), "-o", str(png), str(tmp)], check=True)
    post = [str(png), "-composite"] + brand(pal, s, f"SHELL METRO  ·  {total:,} JOURNEYS  ·  {name.upper()}", corner="southwest")
    write(np.clip(img, 0, 1), out_path("39-shell-metro", f"metro--{name}", s), post)


if __name__ == "__main__":
    names, scale, pals = scheme_args(SCHEMES)
    for nm in names:
        render(nm, pals[nm], scale)
