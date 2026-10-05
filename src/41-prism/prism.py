"""41 — Prism: one white beam through O, M and A cut from thick glass (Blender/Cycles).

The exact O, M and A outlines (src/oma_shapes.py) are extruded into tall slabs of
glass standing on a dark floor. A single narrow white beam crosses the floor and
hits them. The beam is traced in the floor plane with Snell's law at every face it
meets (with total internal reflection), separately for each wavelength, using an
exaggerated Cauchy dispersion so the angled faces of the A and the M notch work as
prisms. Each traced ray becomes a glowing volume beam; the white beam goes in and a
fan of colour comes out. The "spectrum" is the theme's own palette, red to violet.

Path-traced caustics from a thin beam through glass don't converge in Cycles, so
the light paths are computed here and rendered as emissive volumes, with matching
glow strips on the floor.

Usage:
  blender -b -P src/41-prism/prism.py -- --scheme omarchy [--samples 64] [--scale 100]
  blender -b -P src/41-prism/prism.py -- --scheme all
"""
import argparse
import hashlib
import math
import pathlib
import random
import sys

import bmesh
import bpy
from mathutils import Vector

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "palettes"))
sys.path.insert(0, str(ROOT / "src"))
import palettes  # noqa: E402
from bl_brand import sign  # noqa: E402
from oma_shapes import PIECES  # noqa: E402

SCHEMES = ["omarchy", "tokyo-night", "catppuccin", "matte-black"]
OUT = ROOT / "output" / "41-prism"
K = 0.011                                    # svg units -> scene units: logo ~8.4 wide
SPREAD = {"O": -30.0, "M": 0.0, "A": 30.0}
HEIGHT = 1.1                                  # slab height; beams run at mid-height
SPECTRUM = ["red", "orange", "yellow", "green", "cyan", "blue", "magenta"]


def lin(hex_color, k=1.0):
    def f(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = palettes.rgb(hex_color)
    return (f(r) * k, f(g) * k, f(b) * k, 1.0)


def outlines():
    return {k: [((x - 400 + SPREAD[k]) * K, (400 - y) * K) for x, y in fn()] for k, fn in PIECES.items()}


# --- 2D ray tracing through the polygons -------------------------------------------------
def hit(o, d, polys):
    """Nearest intersection of ray o + t d with any polygon edge: (t, point, outward normal) or None."""
    best = None
    for P in polys:
        n = len(P)
        area = sum(P[i][0] * P[(i + 1) % n][1] - P[(i + 1) % n][0] * P[i][1] for i in range(n))
        for i in range(n):
            a, b = Vector(P[i]), Vector(P[(i + 1) % n])
            e = b - a
            den = d.x * e.y - d.y * e.x
            if abs(den) < 1e-12:
                continue
            w = a - o
            t = (w.x * e.y - w.y * e.x) / den
            u = (w.x * d.y - w.y * d.x) / den
            if t > 1e-6 and 0 <= u <= 1 and (best is None or t < best[0]):
                nrm = Vector((e.y, -e.x)).normalized()
                if area > 0:                                   # CCW polygon: outward normal is (e.y, -e.x)
                    pass
                else:
                    nrm = -nrm
                best = (t, o + d * t, nrm)
    return best


def refract(d, nrm, n1, n2):
    """Refract unit d at a surface with unit normal nrm facing against d. None on total internal reflection."""
    cos_i = -nrm.dot(d)
    eta = n1 / n2
    k = 1 - eta * eta * (1 - cos_i * cos_i)
    if k < 0:
        return None
    return (d * eta + nrm * (eta * cos_i - math.sqrt(k))).normalized()


def trace(o, d, polys, n_glass, max_bounce=5, far=16.0):
    """Polyline of a ray through the glass: list of (start, end, inside)."""
    segs, inside = [], False
    for _ in range(max_bounce):
        h = hit(o, d, polys)
        if h is None:
            segs.append((o, o + d * far, inside))
            break
        t, p, nrm = h
        segs.append((o, p, inside))
        if nrm.dot(d) > 0:                                      # leaving: flip the normal to face the ray
            n_face, n1, n2 = -nrm, n_glass, 1.0
        else:
            n_face, n1, n2 = nrm, 1.0, n_glass
        r = refract(d, n_face, n1, n2)
        if r is None:                                           # total internal reflection
            d = (d - n_face * 2 * d.dot(n_face)).normalized()
        else:
            d = r
            inside = not inside
        o = p + d * 1e-5
    return segs


# --- scene ---------------------------------------------------------------------------------
def slab(name, poly, mat):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, 0.0)) for x, y in poly]
    face = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    bmesh.ops.translate(bm, vec=(0, 0, HEIGHT), verts=[v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)
    bev = ob.modifiers.new("bevel", "BEVEL")
    bev.width, bev.segments, bev.limit_method = 0.03, 4, "ANGLE"
    bev.angle_limit = math.radians(30)
    ob.modifiers.new("wn", "WEIGHTED_NORMAL")
    for p in me.polygons:
        p.use_smooth = True
    return ob


def glass():
    m = bpy.data.materials.new("glass")
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.97, 0.98, 1.0, 1)
    p.inputs["Transmission Weight"].default_value = 1.0
    p.inputs["Roughness"].default_value = 0.0
    p.inputs["IOR"].default_value = 1.52
    if "Dispersion" in p.inputs:
        p.inputs["Dispersion"].default_value = 0.5
    return m


def beam_material(color, strength):
    m = bpy.data.materials.new("beam")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Density"].default_value = 0.0
    vol.inputs["Emission Color"].default_value = color
    vol.inputs["Emission Strength"].default_value = strength
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    return m


def floor_glow_material(color, strength):
    """Additive glow on the floor under a beam: emission over transparent, fading across the strip."""
    m = bpy.data.materials.new("floorglow")
    m.use_nodes = True
    m.blend_method = "BLEND" if hasattr(m, "blend_method") else None
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = color
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    add = nt.nodes.new("ShaderNodeAddShader")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs["Vector"])
    # bell across the strip (UV y), fade along it (UV x)
    sub = nt.nodes.new("ShaderNodeMath")
    sub.operation = "SUBTRACT"
    sub.inputs[1].default_value = 0.5
    nt.links.new(sep.outputs["Y"], sub.inputs[0])
    sq = nt.nodes.new("ShaderNodeMath")
    sq.operation = "MULTIPLY"
    nt.links.new(sub.outputs[0], sq.inputs[0])
    nt.links.new(sub.outputs[0], sq.inputs[1])
    ex = nt.nodes.new("ShaderNodeMath")
    ex.operation = "MULTIPLY"
    ex.inputs[1].default_value = -18.0
    nt.links.new(sq.outputs[0], ex.inputs[0])
    bell = nt.nodes.new("ShaderNodeMath")
    bell.operation = "EXPONENT"
    nt.links.new(ex.outputs[0], bell.inputs[0])
    fade = nt.nodes.new("ShaderNodeMath")
    fade.operation = "POWER"
    one = nt.nodes.new("ShaderNodeMath")
    one.operation = "SUBTRACT"
    one.inputs[0].default_value = 1.0
    nt.links.new(sep.outputs["X"], one.inputs[1])
    nt.links.new(one.outputs[0], fade.inputs[0])
    fade.inputs[1].default_value = 0.6
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    nt.links.new(bell.outputs[0], mul.inputs[0])
    nt.links.new(fade.outputs[0], mul.inputs[1])
    mul2 = nt.nodes.new("ShaderNodeMath")
    mul2.operation = "MULTIPLY"
    mul2.inputs[1].default_value = strength
    nt.links.new(mul.outputs[0], mul2.inputs[0])
    nt.links.new(mul2.outputs[0], em.inputs["Strength"])
    nt.links.new(em.outputs["Emission"], add.inputs[0])
    nt.links.new(tr.outputs["BSDF"], add.inputs[1])
    nt.links.new(add.outputs["Shader"], out.inputs["Surface"])
    return m


def box_between(name, a, b, width, z, height, mat):
    """A thin box from a to b (2D points) at height z: one beam segment."""
    a3, b3 = Vector((a.x, a.y, z)), Vector((b.x, b.y, z))
    mid = (a3 + b3) / 2
    L = (b3 - a3).length
    bpy.ops.mesh.primitive_cube_add(size=1, location=mid)
    ob = bpy.context.object
    ob.name = name
    ob.scale = (L, width, height)
    ob.rotation_euler = (0, 0, math.atan2(b.y - a.y, b.x - a.x))
    ob.data.materials.append(mat)
    ob.visible_shadow = False
    return ob


def strip_between(name, a, b, width, mat):
    a3, b3 = Vector((a.x, a.y, 0.002)), Vector((b.x, b.y, 0.002))
    bpy.ops.mesh.primitive_plane_add(size=1, location=(a3 + b3) / 2)
    ob = bpy.context.object
    ob.name = name
    ob.scale = ((b3 - a3).length, width, 1)
    ob.rotation_euler = (0, 0, math.atan2(b.y - a.y, b.x - a.x))
    ob.data.materials.append(mat)
    ob.visible_shadow = False
    return ob


def build(name, pal, samples, scale):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    polys = outlines()
    g = glass()
    for key, poly in polys.items():
        slab(key, poly, g)

    m, nt = bpy.data.materials.new("floor"), None
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = lin(pal["background"], 0.5)
    p.inputs["Roughness"].default_value = 0.8
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 0, 0))
    bpy.context.object.data.materials.append(m)

    # the beam: from the upper left toward a seeded point on the A or the M notch
    ax = sum(q[0] for q in polys["A"]) / len(polys["A"])
    # find beams from the far side that enter the A, cross it once and leave as a clean fan toward the
    # camera (3 segments for every wavelength, nothing else hit); pick one of them by the theme's seed
    P = list(polys.values())
    good = []
    for deg in range(-84, -60, 2):
        d = Vector((math.cos(math.radians(deg)), math.sin(math.radians(deg))))
        for k in range(-8, 9):
            for axo in (-0.5, -0.3, -0.1):
                o = Vector((ax + axo, k * 0.15)) - d * 14
                f = hit(o, d, P)
                if not f or f[1].x < 1.8:
                    continue
                outs = []
                for n in (1.45, 1.65):
                    s = trace(f[1] - d * 1e-4, d, P, n)
                    if len(s) != 3:
                        break
                    v = s[-1][1] - s[-1][0]
                    outs.append(math.atan2(v.y, v.x))
                if len(outs) == 2 and abs(outs[1] - outs[0]) > math.radians(7) and max(outs) < 0:
                    good.append((o, d))
    o0, d0 = rng.choice(good)
    # lift the beam start out of the other pieces: start at the first contact point from far away
    zc = HEIGHT * 0.5
    white = lin(pal.get("bright_foreground", pal["foreground"]))
    spec = [k for k in SPECTRUM if isinstance(pal.get(k), str)]
    first = hit(o0, d0, list(polys.values()))
    entry = first[1] if first else o0 + d0 * 14
    box_between("beam-in", o0, entry, 0.05, zc, 0.05, beam_material(white, 14.0))
    strip_between("glow-in", o0, entry, 0.9, floor_glow_material(white, 0.35))
    for i, key in enumerate(spec):
        n = 1.45 + 0.2 * i / max(len(spec) - 1, 1)               # exaggerated Cauchy dispersion, red -> violet
        col = lin(pal[key])
        segs = trace(entry - d0 * 1e-4, d0, list(polys.values()), n)
        bm = beam_material(col, 4.0)
        fm = floor_glow_material(col, 0.5)
        for j, (a, b, inside) in enumerate(segs):
            if inside:
                box_between(f"in-{key}-{j}", a, b, 0.03, zc, 0.03, beam_material(col, 3.0))
            else:
                box_between(f"out-{key}-{j}", a, b, 0.05, zc, 0.05, bm)
                strip_between(f"glow-{key}-{j}", a, b, 0.7, fm)

    # a dim glowing backdrop far behind, so the glass has something to bend
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 9, 2.5), rotation=(math.radians(90), 0, 0))
    wall = bpy.context.object
    wall.scale = (40, 9, 1)
    wm = bpy.data.materials.new("backdrop")
    wm.use_nodes = True
    wnt = wm.node_tree
    for n in list(wnt.nodes):
        wnt.nodes.remove(n)
    wo = wnt.nodes.new("ShaderNodeOutputMaterial")
    we = wnt.nodes.new("ShaderNodeEmission")
    tc = wnt.nodes.new("ShaderNodeTexCoord")
    sep = wnt.nodes.new("ShaderNodeSeparateXYZ")
    wnt.links.new(tc.outputs["UV"], sep.inputs["Vector"])
    cr = wnt.nodes.new("ShaderNodeValToRGB")                   # glow along the horizon, dark above
    cr.color_ramp.elements[0].color = lin(pal.get("lighter_background", pal["background"]), 1.6)
    cr.color_ramp.elements[1].position = 0.55
    cr.color_ramp.elements[1].color = lin(pal["background"], 0.2)
    wnt.links.new(sep.outputs["Y"], cr.inputs["Fac"])
    wnt.links.new(cr.outputs["Color"], we.inputs["Color"])
    we.inputs["Strength"].default_value = 1.0
    wnt.links.new(we.outputs["Emission"], wo.inputs["Surface"])
    wall.data.materials.append(wm)

    # rim lights only seen in the glass edges
    for loc, col, e in (((-7, 6, 4), lin(pal["accent"]), 500), ((8, 5, 3.5), lin(pal.get("blue", pal["accent"])), 400)):
        ld = bpy.data.lights.new("rim", "AREA")
        ld.size, ld.energy, ld.color = 5, e, col[:3]
        ob = bpy.data.objects.new("rim", ld)
        sc.collection.objects.link(ob)
        ob.location = loc
        ob.rotation_euler = (Vector((0, 0, 0.5)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        ob.visible_diffuse = False

    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = lin(pal["background"])
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    sc.world = world

    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = 38
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    target = Vector((0.6, -0.6, 0.9))
    elev, azim = math.radians(rng.uniform(17, 22)), math.radians(-90 + rng.uniform(-8, 8))
    dist = 15.0
    cam.location = target + Vector((dist * math.cos(elev) * math.cos(azim), dist * math.cos(elev) * math.sin(azim),
                                    dist * math.sin(elev)))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam

    r = sc.render
    r.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 16
    sc.cycles.transmission_bounces = 16
    sc.cycles.volume_bounces = 0
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
        out = OUT / f"prism--{name}.png" if args.scale == 100 else ROOT / ".wip" / f"prism--{name}@{args.scale}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        bpy.context.scene.render.filepath = str(out)
        bpy.ops.render.render(write_still=True)
        sign(out, pal, args.scale / 100, f"PRISM  ·  {name.upper()}")
        print("wrote", out)


main()
