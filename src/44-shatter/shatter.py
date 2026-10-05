"""44 — Shatter: a glass OMA pane a few milliseconds after the hit (Blender/Cycles).

The exact O, M and A outlines (src/oma_shapes.py) stand upright as one pane of thick
glass in front of a wall of glowing app icons. Something has just gone through it:
each piece is broken into Voronoi shards, dense and small around the impact point and
large toward the edges (cells clipped from the outline with half-planes, then
extruded). Every shard has flown outward and toward the camera with a speed that falls
off with its distance from the impact, and spins; a spray of chips and glass dust
follows the exit cone. The icons behind are bent through every shard.
The impact point, the cell layout and the camera are seeded from the theme name.

Usage:
  blender -b -P src/44-shatter/shatter.py -- --scheme omarchy [--samples 64] [--scale 100]
  blender -b -P src/44-shatter/shatter.py -- --scheme all
"""
import argparse
import hashlib
import math
import pathlib
import random
import sys

import bmesh
import bpy
from mathutils import Euler, Vector

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "palettes"))
sys.path.insert(0, str(ROOT / "src"))
import palettes  # noqa: E402
from bl_brand import sign  # noqa: E402
from oma_shapes import PIECES  # noqa: E402

SCHEMES = ["omarchy", "tokyo-night", "hackerman", "osaka-jade"]
OUT = ROOT / "output" / "44-shatter"
ICONS = ROOT / "src" / "24-oma-dome" / "icons.png"
K = 0.01                                     # svg units -> scene units: the pane is ~7.6 wide
THICK = 0.28
SPREAD = {"O": -20.0, "M": 0.0, "A": 20.0}


def lin(hex_color, k=1.0):
    def f(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = palettes.rgb(hex_color)
    return (f(r) * k, f(g) * k, f(b) * k, 1.0)


def outlines():
    return {k: [((x - 400 + SPREAD[k]) * K, (400 - y) * K) for x, y in fn()] for k, fn in PIECES.items()}


def clip_half(poly, p, n):
    """Sutherland–Hodgman: keep the part of poly where (q - p)·n <= 0."""
    out = []
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        da = (a[0] - p[0]) * n[0] + (a[1] - p[1]) * n[1]
        db = (b[0] - p[0]) * n[0] + (b[1] - p[1]) * n[1]
        if da <= 0:
            out.append(a)
        if (da <= 0) != (db <= 0):
            t = da / (da - db)
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def area(poly):
    return 0.5 * abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                         for i in range(len(poly))))


def voronoi_cells(poly, sites):
    cells = []
    for i, s in enumerate(sites):
        cell = list(poly)
        for j, t in enumerate(sites):
            if i == j or not cell:
                continue
            mid = ((s[0] + t[0]) / 2, (s[1] + t[1]) / 2)
            cell = clip_half(cell, mid, (t[0] - s[0], t[1] - s[1]))
        if len(cell) >= 3 and area(cell) > 1e-4:
            cells.append((s, cell))
    return cells


def shard(name, cell, mat):
    """Extrude a 2D cell (x, z) into a shard of the pane, centred on its own origin."""
    cx = sum(p[0] for p in cell) / len(cell)
    cz = sum(p[1] for p in cell) / len(cell)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vs = [bm.verts.new((x - cx, -THICK / 2, z - cz)) for x, z in cell]
    try:
        face = bm.faces.new(vs)
    except ValueError:
        bm.free()
        return None
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    bmesh.ops.translate(bm, vec=(0, THICK, 0), verts=[v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)
    bev = ob.modifiers.new("bevel", "BEVEL")
    bev.width, bev.segments = 0.008, 2
    return ob, Vector((cx, 0, cz))


def glass(pal):
    m = bpy.data.materials.new("glass")
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    t = lin(pal["accent"])
    p.inputs["Base Color"].default_value = tuple(0.88 + 0.12 * c for c in t[:3]) + (1,)
    p.inputs["Transmission Weight"].default_value = 1.0
    p.inputs["Roughness"].default_value = 0.0
    p.inputs["IOR"].default_value = 1.52
    if "Dispersion" in p.inputs:
        p.inputs["Dispersion"].default_value = 0.4
    return m


def icon_wall(pal):
    m = bpy.data.materials.new("iconwall")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(ICONS))
    tex.image.colorspace_settings.name = "Non-Color"
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 1.0, 1)
    nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = lin(pal["background"], 0.8)
    mix.inputs["B"].default_value = lin(pal["accent"])
    nt.links.new(tex.outputs["Color"], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], em.inputs["Color"])
    # brighter in the middle, fading to the edges
    grad = nt.nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "SPHERICAL"
    mp2 = nt.nodes.new("ShaderNodeMapping")
    mp2.inputs["Scale"].default_value = (1.0, 1.8, 1)
    nt.links.new(tc.outputs["Object"], mp2.inputs["Vector"])
    nt.links.new(mp2.outputs["Vector"], grad.inputs["Vector"])
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY_ADD"
    mul.inputs[1].default_value = 1.3
    mul.inputs[2].default_value = 0.15
    nt.links.new(grad.outputs["Fac"], mul.inputs[0])
    nt.links.new(mul.outputs[0], em.inputs["Strength"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


def build(name, pal, samples, scale):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    g = glass(pal)
    polys = outlines()
    hit_key = rng.choice(["M", "M", "O", "A"])
    hp = polys[hit_key]
    hx = sum(p[0] for p in hp) / len(hp) + rng.uniform(-0.4, 0.4)
    hz = sum(p[1] for p in hp) / len(hp) + rng.uniform(-0.4, 0.4)
    impact = Vector((hx, 0, hz))

    for key, poly in polys.items():
        xs, zs = [p[0] for p in poly], [p[1] for p in poly]
        sites = []
        while len(sites) < 46:
            r = rng.expovariate(1 / 0.9) if key == hit_key else rng.uniform(0, 1) * 4
            a = rng.uniform(0, 2 * math.pi)
            # radial cracks: cells stretched along rays from the impact
            s = (hx + r * math.cos(a), hz + r * math.sin(a) * 0.9)
            if key != hit_key:
                s = (rng.uniform(min(xs), max(xs)), rng.uniform(min(zs), max(zs)))
            if min(xs) - 0.1 < s[0] < max(xs) + 0.1 and min(zs) - 0.1 < s[1] < max(zs) + 0.1:
                sites.append(s)
        if key != hit_key:
            sites = sites[:rng.randint(5, 9)]
        for i, (s, cell) in enumerate(voronoi_cells(poly, sites)):
            made = shard(f"{key}{i}", cell, g)
            if not made:
                continue
            ob, c = made
            d = c - impact
            dist = d.length + 0.25
            v = 0.55 / dist ** 1.2                                  # speed falls off with distance
            outward = Vector((d.x, 0, d.z)).normalized() if d.length > 1e-6 else Vector((0, 0, 1))
            ob.location = c + outward * v * 1.6 + Vector((0, -v * 2.4, -v * 0.3))
            spin = v * 2.2
            ob.rotation_euler = Euler((rng.uniform(-spin, spin), rng.uniform(-spin, spin), rng.uniform(-spin, spin)))

    # chips and dust: a spray of tiny tetrahedra in the exit cone toward the camera
    me = bpy.data.meshes.new("chips")
    bm = bmesh.new()
    for _ in range(1400):
        r = rng.expovariate(1 / 0.5)
        a = rng.uniform(0, 2 * math.pi)
        depth = rng.uniform(0.1, 3.2)
        cen = impact + Vector((math.cos(a) * r * (0.3 + depth * 0.25), -depth, math.sin(a) * r * (0.3 + depth * 0.25)))
        sz = rng.uniform(0.006, 0.04) * (1.4 if rng.random() < 0.1 else 1)
        vs = [bm.verts.new(cen + Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))) * sz)
              for _ in range(4)]
        for f in ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)):
            try:
                bm.faces.new([vs[i] for i in f])
            except ValueError:
                pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    chips = bpy.data.objects.new("chips", me)
    sc.collection.objects.link(chips)
    chips.data.materials.append(g)

    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 3.2, 0.2), rotation=(math.radians(90), 0, 0))
    wall = bpy.context.object
    wall.scale = (22, 12, 1)
    wall.data.materials.append(icon_wall(pal))

    # specular-only softboxes so every shard edge catches a line of light
    for loc, col, e in (((-5, -4, 4), lin(pal.get("bright_foreground", pal["foreground"])), 900),
                        ((5, -3, -2), lin(pal["accent"]), 220)):
        ld = bpy.data.lights.new("box", "AREA")
        ld.size, ld.energy, ld.color = 4, e, col[:3]
        ob = bpy.data.objects.new("box", ld)
        sc.collection.objects.link(ob)
        ob.location = loc
        ob.rotation_euler = (Vector((0, 0, 0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        ob.visible_diffuse = False

    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = lin(pal["background"])
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.2
    sc.world = world

    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = 40
    cam_d.dof.use_dof = True
    cam_d.dof.aperture_fstop = 3.5
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    target = Vector((0, -0.6, 0))
    az = math.radians(-90 + rng.choice([-1, 1]) * rng.uniform(20, 30))       # turned ~25° so the glass reads
    el = math.radians(rng.uniform(4, 10))
    dist = 12.5
    cam.location = target + Vector((dist * math.cos(el) * math.cos(az), dist * math.cos(el) * math.sin(az),
                                    dist * math.sin(el)))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam_d.dof.focus_distance = (impact - cam.location).length
    sc.camera = cam

    r = sc.render
    r.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 16
    sc.cycles.transmission_bounces = 16
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
        out = OUT / f"shatter--{name}.png" if args.scale == 100 else ROOT / ".wip" / f"shatter--{name}@{args.scale}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        bpy.context.scene.render.filepath = str(out)
        bpy.ops.render.render(write_still=True)
        sign(out, pal, args.scale / 100, f"SHATTER  ·  {name.upper()}")
        print("wrote", out)


main()
