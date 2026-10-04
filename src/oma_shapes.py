"""Exact outlines of the three OMA logo pieces (from assets/brand/oma-logo.svg).

SVG units, viewBox 800x800, y down. Shared by Blender scripts that need the
circle (O), notched square (M) and diamond (A) as polygons.
"""
import math

CX, CY, R = 188.0, 400.0, 149.0          # the circle the O and the M's bite share
A0 = math.acos((283.0 - CX) / R)          # where the circle meets the x=283 chord


def arc(a_from, a_to, steps=72):
    return [(CX + R * math.cos(a_from + (a_to - a_from) * i / steps),
             CY + R * math.sin(a_from + (a_to - a_from) * i / steps)) for i in range(steps + 1)]


def o_piece():
    """Left piece: the big arc of the circle closed by the x=283 chord."""
    return arc(A0, 2 * math.pi - A0, 160)


def m_piece():
    """Square with the circle's bulge bitten from its left side and a V notch on the right."""
    return ([(283.0, 262.0), (536.0, 262.0), (536.0, 326.0), (462.0, 400.0),
             (536.0, 474.0), (536.0, 536.0), (283.0, 536.0)] + arc(A0, -A0, 72))


def a_piece():
    return [(536.0, 326.0), (610.5, 251.5), (759.0, 400.0), (610.5, 548.5), (536.0, 474.0)]


def normalized(poly, size=1.0):
    """Centre a polygon on its bounding box and scale its larger side to `size` (y flipped to up)."""
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    k = size / max(max(xs) - min(xs), max(ys) - min(ys))
    return [((x - cx) * k, (cy - y) * k) for x, y in poly]


PIECES = {"O": o_piece, "M": m_piece, "A": a_piece}
