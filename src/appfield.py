"""Shared machinery for the app-icon pieces (11 App Galaxy and the 13+ remixes).

* Atlas: Nerd Font glyphs rendered once per (codepoint, pixel size) as alpha masks
* Canvas: an RGB "over" layer you stamp glyphs onto, with optional rotation,
  anisotropic stretch along any axis, and motion-trail repeats
* Camera / splat: perspective projection and bilinear additive point splatting
* finish(): bloom + filmic tone map over a background, plus Omarchy branding
"""
import math
import pathlib
import subprocess

import numpy as np

from common import BRAND, FONTS, ROOT, box_blur, hex2arr, save_rgb

FONT = FONTS / "Iosevka" / "IosevkaNerdFontMono-Regular.ttf"
CORE = [0xF303, 0xF17C, 0xF359, 0xF489, 0xF120, 0xF08C7]                 # arch, linux, hypr, term
APPS = [0xF269, 0xF268, 0xE7C5, 0xF338, 0xE795, 0xF308, 0xE73C, 0xE739, 0xE791, 0xF1BC,
        0xF167, 0xE60B, 0xF0E0, 0xF1C0, 0xE706, 0xE7B1, 0xF07B, 0xF015, 0xF001, 0xF03D,
        0xF030, 0xF11B, 0xF1FC, 0xF0AD, 0xF121, 0xF126, 0xF09B, 0xF113, 0xF0AB0, 0xF0B79,
        0xF07B7, 0xF0A1E, 0xF0517, 0xF2DC, 0xF0C2, 0xF1B2, 0xF1EB, 0xE702, 0xF418, 0xE62B,
        0xE7A8, 0xE627, 0xE74E, 0xE620, 0xE718, 0xF013, 0xF233, 0xE615, 0xE61D, 0xE737, 0xF0219]
ROCKET = 0xF135


class Atlas:
    """Lazily rendered glyph alpha masks per (codepoint, pixel size), cached on disk."""

    def __init__(self, cache=ROOT / ".wip" / "atlas"):
        self.cache = pathlib.Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.mem = {}

    def get(self, cp, px):
        px = max(int(px), 4)
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


def quantize(px, s):
    """Snap a pixel size to a small set so the atlas cache stays small."""
    sizes = np.unique(np.maximum((np.geomspace(8, 220, 22) * s).astype(int), 4))
    return int(sizes[np.argmin(np.abs(sizes - px))])


def warp(mask, A):
    """Resample a glyph mask through the 2x2 linear map A (glyph -> screen), bilinear."""
    h, w = mask.shape
    corners = np.array([[-w / 2, -h / 2], [w / 2, -h / 2], [-w / 2, h / 2], [w / 2, h / 2]]) @ A.T
    hw = int(np.ceil(np.abs(corners[:, 0]).max())) + 1
    hh = int(np.ceil(np.abs(corners[:, 1]).max())) + 1
    yy, xx = np.mgrid[-hh:hh + 1, -hw:hw + 1].astype(np.float32)
    inv = np.linalg.inv(A)
    u = inv[0, 0] * xx + inv[0, 1] * yy + w / 2 - 0.5
    v = inv[1, 0] * xx + inv[1, 1] * yy + h / 2 - 0.5
    u0, v0 = np.floor(u).astype(int), np.floor(v).astype(int)
    fu, fv = u - u0, v - v0
    out = np.zeros_like(u)
    for du, dv, wt in ((0, 0, (1 - fu) * (1 - fv)), (1, 0, fu * (1 - fv)), (0, 1, (1 - fu) * fv), (1, 1, fu * fv)):
        uu, vv = u0 + du, v0 + dv
        ok = (uu >= 0) & (uu < w) & (vv >= 0) & (vv < h)
        out[ok] += mask[vv[ok], uu[ok]] * wt[ok]
    return out


def affine(angle=0.0, stretch=1.0, squash=1.0, axis=0.0):
    """Rotation by `angle`, then stretch along direction `axis` and squash across it."""
    ca, sa = math.cos(axis), math.sin(axis)
    D = np.array([[ca, -sa], [sa, ca]])
    S = D @ np.diag([stretch, squash]) @ D.T
    cr, sr = math.cos(angle), math.sin(angle)
    return S @ np.array([[cr, -sr], [sr, cr]])


class Canvas:
    """Premultiplied RGB + alpha layer for glyph stamping (painter's order: call far -> near)."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.rgb = np.zeros((h, w, 3), np.float32)
        self.a = np.zeros((h, w), np.float32)

    def stamp(self, mask, x, y, color, alpha=1.0, A=None):
        if A is not None:
            mask = warp(mask, A)
        mh, mw = mask.shape
        x0, y0 = int(round(x - mw / 2)), int(round(y - mh / 2))
        xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + mw, self.w), min(y0 + mh, self.h)
        if xa >= xb or ya >= yb:
            return
        m = np.clip(mask[ya - y0:yb - y0, xa - x0:xb - x0] * alpha, 0, 1)
        self.rgb[ya:yb, xa:xb] = self.rgb[ya:yb, xa:xb] * (1 - m[..., None]) + np.asarray(color) * m[..., None]
        self.a[ya:yb, xa:xb] = self.a[ya:yb, xa:xb] * (1 - m) + m

    def trail(self, mask, pts, color, alpha=1.0, A=None, power=1.6):
        """Stamp a glyph repeatedly along pts (oldest first): a fading motion trail."""
        if A is not None:
            mask = warp(mask, A)
        n = len(pts)
        for k, (x, y) in enumerate(pts):
            head = k == n - 1
            ghost = 0.35 * ((k + 1) / n) ** power
            self.stamp(mask, x, y, color, alpha * (1.0 if head else ghost))


class Camera:
    def __init__(self, elev_deg, azim_deg, dist, w, h, fov_deg=38, target=(0, 0, 0)):
        e, a = math.radians(elev_deg), math.radians(azim_deg)
        t = np.asarray(target, float)
        self.pos = t + np.array([dist * math.cos(e) * math.cos(a), dist * math.cos(e) * math.sin(a), dist * math.sin(e)])
        fwd = (t - self.pos) / np.linalg.norm(t - self.pos)
        right = np.cross(fwd, [0, 0, 1])
        right /= np.linalg.norm(right)
        up = np.cross(right, fwd)
        self.R = np.stack([right, up, fwd])
        self.f = (w / 2) / math.tan(math.radians(fov_deg) / 2)
        self.cx, self.cy = w / 2, h / 2

    def project(self, p):
        c = (np.asarray(p) - self.pos) @ self.R.T
        depth = c[..., 2]
        return self.cx + self.f * c[..., 0] / depth, self.cy - self.f * c[..., 1] / depth, depth


def splat(acc, xs, ys, color, weight):
    """Bilinear additive splat of points into an (h, w, 3) buffer."""
    h, w, _ = acc.shape
    xs, ys = np.asarray(xs, np.float32), np.asarray(ys, np.float32)
    color = np.broadcast_to(np.asarray(color, np.float32), (xs.size, 3)) if np.ndim(color) == 1 else color
    weight = np.broadcast_to(np.asarray(weight, np.float32), xs.shape)
    x0, y0 = np.floor(xs).astype(int), np.floor(ys).astype(int)
    fx, fy = xs - x0, ys - y0
    for dx, dy, wt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = x0 + dx, y0 + dy
        ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
        np.add.at(acc, (yi[ok], xi[ok]), color[ok] * (weight * wt)[ok, None])


def blur3(img, r):
    return np.stack([box_blur(img[..., i], r) for i in range(3)], -1)


def finish(light, pal, s, bloom=1.0, exposure=1.25, vignette=0.35):
    """Tone-map an additive light buffer over a vertical background gradient."""
    h, w, _ = light.shape
    bg, dark = hex2arr(pal["background"]), hex2arr(pal.get("darker_background", pal["background"]))
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    base = bg * (1 - yy) + dark * yy
    xx = np.linspace(-1, 1, w, dtype=np.float32)[None, :, None]
    base = base * (1 - vignette * np.clip(xx ** 2 * 0.5 + (yy - 0.5) ** 2 * 1.2, 0, 1))
    if bloom:
        light = light + blur3(light, 14 * s * 2) * 0.5 * bloom + blur3(light, 60 * s * 2) * 0.35 * bloom
    return base + (1 - np.exp(-light * exposure)) * (1 - base)


def brand(pal, s, caption, corner="southwest"):
    """ImageMagick ops: the Omarchy wordmark + a small caption in a corner."""
    font = str(FONTS / "SpaceMono" / "SpaceMonoNerdFontMono-Regular.ttf")
    m = int(110 * s)
    dim = pal.get("dark_foreground", pal["foreground"])
    return ["(", str(BRAND / "omarchy-wordmark.png"), "-alpha", "extract", "-resize", f"{int(460 * s)}x",
            "-background", pal["accent"], "-alpha", "shape", "-channel", "A", "-evaluate", "multiply", "0.85",
            "+channel", ")", "-gravity", corner, "-geometry", f"+{m}+{m + int(44 * s)}", "-composite",
            "-font", font, "-pointsize", str(max(int(24 * s), 7)), "-fill", dim, "-kerning", str(max(int(6 * s), 1)),
            "-gravity", corner, "-annotate", f"+{m}+{m}", caption]


def write(img, path, post=()):
    save_rgb(img, path, list(post))
