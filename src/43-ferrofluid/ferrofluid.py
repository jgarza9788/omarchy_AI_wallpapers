"""43 — Ferrofluid: a black pool over hidden O, M and A magnets (Blender/Cycles).

A shallow pool of ferrofluid sits over three magnets cut in the exact O, M and A
outlines (src/oma_shapes.py), which are never shown. Above a critical field the flat
surface goes unstable (the Rosensweig instability) and stands up in a hexagonal
lattice of sharp, concave-flanked spikes. The spikes are tallest where the field is
strongest, deep inside each magnet, and shrink to ripples at its edge, so the logo
appears only as a field of black thorns. The fluid is a near-perfect black mirror,
so all you see is the theme-coloured softboxes sliding along the spikes.

The heightfield is built in numpy (hex lattice, one cone-ish spike per site, plus a
soft mound) and loaded as a single grid mesh.

Usage:
  blender -b -P src/43-ferrofluid/ferrofluid.py -- --scheme omarchy [--samples 64] [--scale 100]
  blender -b -P src/43-ferrofluid/ferrofluid.py -- --scheme all
"""
import argparse
import hashlib
import math
import pathlib
import sys

import bpy
import numpy as np
from mathutils import Vector

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "palettes"))
sys.path.insert(0, str(ROOT / "src"))
import palettes  # noqa: E402
from bl_brand import sign  # noqa: E402
from oma_shapes import PIECES  # noqa: E402

SCHEMES = ["omarchy", "tokyo-night", "catppuccin", "gruvbox"]
OUT = ROOT / "output" / "43-ferrofluid"
K = 0.0125                                   # svg units -> scene units: the logo is ~9.4 wide
SPREAD = {"O": -40.0, "M": 0.0, "A": 40.0}   # pull the pieces apart so each magnet has its own field
GX, GY, RES = 15.0, 8.5, 0.012               # heightfield extent and cell size
A_LAT = 0.3                                  # spike spacing


def lin(hex_color, k=1.0):
    def f(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = palettes.rgb(hex_color)
    return (f(r) * k, f(g) * k, f(b) * k, 1.0)


def polys():
    out = []
    for key, fn in PIECES.items():
        out.append(np.array([((x - 400 + SPREAD[key]) * K, (400 - y) * K) for x, y in fn()]))
    return out


def depth_inside(pts, polygons):
    """Signed distance into the nearest magnet (positive inside), for an (n, 2) array of points."""
    best = np.full(len(pts), -1e9)
    for P in polygons:
        a, b = P, np.roll(P, -1, 0)
        inside = np.zeros(len(pts), bool)
        dmin = np.full(len(pts), 1e9)
        for (x1, y1), (x2, y2) in zip(a, b):
            if (y1 > pts[:, 1]).any() or (y2 > pts[:, 1]).any():
                cross = ((y1 > pts[:, 1]) != (y2 > pts[:, 1])) & \
                        (pts[:, 0] < (x2 - x1) * (pts[:, 1] - y1) / (y2 - y1 + 1e-12) + x1)
                inside ^= cross
            ex, ey = x2 - x1, y2 - y1
            t = np.clip(((pts[:, 0] - x1) * ex + (pts[:, 1] - y1) * ey) / (ex * ex + ey * ey + 1e-12), 0, 1)
            dmin = np.minimum(dmin, np.hypot(pts[:, 0] - x1 - t * ex, pts[:, 1] - y1 - t * ey))
        best = np.maximum(best, np.where(inside, dmin, -dmin))
    return best


def heightfield(rng):
    nx, ny = int(GX / RES), int(GY / RES)
    xs = np.linspace(-GX / 2, GX / 2, nx)
    ys = np.linspace(-GY / 2, GY / 2, ny)
    z = np.zeros((ny, nx), np.float32)
    mound = np.zeros((ny, nx), np.float32)
    P = polys()
    # hex lattice of spike sites, jittered a little
    rows = []
    for j in range(int(GY / (A_LAT * 0.866)) + 1):
        y = -GY / 2 + j * A_LAT * 0.866
        off = (j % 2) * A_LAT / 2
        for i in range(int(GX / A_LAT) + 1):
            rows.append((-GX / 2 + off + i * A_LAT, y))
    sites = np.array(rows) + rng.normal(0, A_LAT * 0.04, (len(rows), 2))
    d = depth_inside(sites, P)
    field = np.clip((d + 0.12) / 0.75, 0, 1) ** 0.8               # strongest deep inside each magnet
    keep = field > 0.02
    sites, field = sites[keep], field[keep]
    hmax = 0.5
    r = A_LAT * 0.8
    for (sx, sy), f in zip(sites, field):
        h = hmax * f * rng.uniform(0.85, 1.1)
        rr = r * (0.75 + 0.25 * f)
        i0, i1 = np.searchsorted(xs, [sx - rr * 2.2, sx + rr * 2.2])
        j0, j1 = np.searchsorted(ys, [sy - rr * 2.2, sy + rr * 2.2])
        X, Y = np.meshgrid(xs[i0:i1], ys[j0:j1])
        dd = np.hypot(X - sx, Y - sy)
        spike = h * np.clip(1 - dd / rr, 0, 1) ** 1.6              # concave flanks, sharp tip
        z[j0:j1, i0:i1] = np.maximum(z[j0:j1, i0:i1], spike)
        mound[j0:j1, i0:i1] += 0.05 * f * np.exp(-(dd / (rr * 1.3)) ** 2)
    return xs, ys, z + mound


def grid_mesh(name, xs, ys, z):
    ny, nx = z.shape
    X, Y = np.meshgrid(xs, ys)
    co = np.stack([X, Y, z], -1).reshape(-1, 3).astype(np.float32)
    idx = np.arange(nx * ny).reshape(ny, nx)
    quads = np.stack([idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]], -1).reshape(-1, 4)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(co))
    me.vertices.foreach_set("co", co.ravel())
    me.loops.add(quads.size)
    me.loops.foreach_set("vertex_index", quads.ravel().astype(np.int32))
    me.polygons.add(len(quads))
    me.polygons.foreach_set("loop_start", np.arange(0, quads.size, 4, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(len(quads), 4, np.int32))
    me.update(calc_edges=True)
    me.validate()
    me.polygons.foreach_set("use_smooth", np.ones(len(quads), bool))
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def fluid_material():
    m = bpy.data.materials.new("ferrofluid")
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.004, 0.004, 0.005, 1)
    p.inputs["Roughness"].default_value = 0.07
    p.inputs["Metallic"].default_value = 0.35
    p.inputs["Coat Weight"].default_value = 1.0
    p.inputs["Coat Roughness"].default_value = 0.02
    return m


def softbox(name, loc, target, color, energy, size, visible=False):
    ld = bpy.data.lights.new(name, "AREA")
    ld.shape, ld.size, ld.size_y = "RECTANGLE", size[0], size[1]
    ld.energy, ld.color = energy, color[:3]
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    ob.visible_camera = visible
    return ob


def emissive_strip(name, loc, scale, color, strength, rot=(math.radians(90), 0, 0)):
    """A glowing panel far behind the pool: the long reflection streaks along every spike."""
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc, rotation=rot)
    ob = bpy.context.object
    ob.name = name
    ob.scale = scale
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = color
    em.inputs["Strength"].default_value = strength
    # soft fade towards the panel's ends
    tc = nt.nodes.new("ShaderNodeTexCoord")
    grad = nt.nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "SPHERICAL"
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 2.5, 1)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], grad.inputs["Vector"])
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = strength
    nt.links.new(grad.outputs["Fac"], mul.inputs[0])
    nt.links.new(mul.outputs[0], em.inputs["Strength"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    ob.data.materials.append(m)
    ob.visible_camera = False
    return ob


def build(name, pal, samples, scale):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    mat = fluid_material()
    xs, ys, z = heightfield(rng)
    pool = grid_mesh("pool", xs, ys, z)
    pool.data.materials.append(mat)
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -0.0005))
    bpy.context.object.data.materials.append(mat)

    # lights: a key softbox in the accent, a cool rim, a warm low kicker, and a long strip behind
    acc = lin(pal["accent"])
    cool = lin(pal.get("blue", pal["accent"]))
    warm = lin(pal.get("magenta", pal.get("red", pal["accent"])))
    side = 1 if rng.random() < 0.5 else -1
    softbox("key", (side * 6, -4, 6), (0, 0, 0.3), acc, 1600, (6, 2.5))
    softbox("rim", (-side * 7, 7, 6.5), (0, 0, 0.3), cool, 1800, (8, 1.5))
    softbox("top", (0, 1.5, 9), (0, 0, 0), lin(pal.get("bright_foreground", pal["foreground"])), 900, (14, 5))

    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = lin(pal["background"])
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.25
    sc.world = world

    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = 55
    cam_d.dof.use_dof = True
    cam_d.dof.aperture_fstop = 2.4
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    target = Vector((0, 0.3, 0.2))
    elev, azim = math.radians(rng.uniform(24, 30)), math.radians(-90 + rng.uniform(-14, 14))
    dist = 17.5
    cam.location = target + Vector((dist * math.cos(elev) * math.cos(azim), dist * math.cos(elev) * math.sin(azim),
                                    dist * math.sin(elev)))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam_d.dof.focus_distance = (target - cam.location).length
    sc.camera = cam

    r = sc.render
    r.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 8
    r.resolution_x, r.resolution_y, r.resolution_percentage = 3840, 2160, scale
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Punchy"


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheme", default="omarchy")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--scale", type=int, default=100)
    args = ap.parse_args(argv)
    for name in (SCHEMES if args.scheme == "all" else [args.scheme]):
        pal = palettes.load()[name]
        build(name, pal, args.samples, args.scale)
        out = OUT / f"ferrofluid--{name}.png" if args.scale == 100 else ROOT / ".wip" / f"ferrofluid--{name}@{args.scale}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        bpy.context.scene.render.filepath = str(out)
        bpy.ops.render.render(write_still=True)
        sign(out, pal, args.scale / 100, f"FERROFLUID  ·  {name.upper()}")
        print("wrote", out)


main()
