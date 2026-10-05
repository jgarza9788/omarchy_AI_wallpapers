"""42 — Neon: the O, M and A outlines bent from real neon tubing (Blender/Cycles).

Each exact outline (src/oma_shapes.py) is a glass tube: a thin emissive gas core inside
a clear sleeve, held off a rough concrete wall by little standoff clips, with a
power cable dropping to the floor. Below, a rain-wet floor of dark concrete has
puddles (a noise mask switches roughness between mirror-wet and matte), so the
reflection of the sign breaks up. The tubes light the wall themselves. One of the
three tubes is failing and glows only faintly. Colours, the failing tube and the
camera angle are seeded from the theme name.

Usage:
  blender -b -P src/42-neon/neon.py -- --scheme omarchy [--samples 64] [--scale 100]
  blender -b -P src/42-neon/neon.py -- --scheme all
"""
import argparse
import hashlib
import math
import pathlib
import random
import sys

import bpy
from mathutils import Vector

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "palettes"))
sys.path.insert(0, str(ROOT / "src"))
import palettes  # noqa: E402
from bl_brand import sign  # noqa: E402
from oma_shapes import PIECES  # noqa: E402

SCHEMES = ["omarchy", "tokyo-night", "retro-82", "kanagawa"]
OUT = ROOT / "output" / "42-neon"
K = 0.0062                                  # svg units -> metres: the sign is ~3.2 m wide
SPREAD = {"O": -26.0, "M": 0.0, "A": 26.0}
Z0 = 1.85                                   # sign centre height
WALL_Y = 0.0


def lin(hex_color, k=1.0):
    def f(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = palettes.rgb(hex_color)
    return (f(r) * k, f(g) * k, f(b) * k, 1.0)


def nodes_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m, m.node_tree, m.node_tree.nodes["Principled BSDF"]


def outline(key, inset=0.0):
    pts = [((x - 400 + SPREAD[key]) * K, WALL_Y - 0.12, (400 - y) * K + Z0) for x, y in PIECES[key]()]
    return pts


def tube(name, pts, radius, mat):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth, cu.bevel_resolution = radius, 5
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p, (x, y, z) in zip(sp.points, pts):
        p.co = (x, y, z, 1)
    sp.use_cyclic_u = True
    ob = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)
    # round the polygon corners into bends
    return ob


def gas(color, strength):
    m = bpy.data.materials.new("gas")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = color
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


def sleeve_glass(color):
    m, nt, p = nodes_mat("sleeve")
    p.inputs["Base Color"].default_value = tuple(0.75 + 0.25 * c for c in color[:3]) + (1,)
    p.inputs["Transmission Weight"].default_value = 1.0
    p.inputs["Roughness"].default_value = 0.05
    p.inputs["IOR"].default_value = 1.47
    return m


def concrete(pal, base_k=0.12):
    m, nt, p = nodes_mat("concrete")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 9.0
    nz.inputs["Detail"].default_value = 12.0
    nz.inputs["Roughness"].default_value = 0.65
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = lin(pal["background"], 0.6)
    ramp.color_ramp.elements[1].color = (0.32 * base_k * 4, 0.32 * base_k * 4, 0.33 * base_k * 4, 1)
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.9
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    bump.inputs["Distance"].default_value = 0.01
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    return m


def wet_floor(pal):
    m, nt, p = nodes_mat("wet")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.9
    nz.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    puddle = nt.nodes.new("ShaderNodeValToRGB")            # wet (mirror) where the noise is low
    puddle.color_ramp.elements[0].position, puddle.color_ramp.elements[1].position = 0.46, 0.52
    puddle.color_ramp.elements[0].color = (0.02, 0.02, 0.02, 1)
    puddle.color_ramp.elements[1].color = (0.55, 0.55, 0.55, 1)
    nt.links.new(nz.outputs["Fac"], puddle.inputs["Fac"])
    nt.links.new(puddle.outputs["Color"], p.inputs["Roughness"])
    grit = nt.nodes.new("ShaderNodeTexNoise")
    grit.inputs["Scale"].default_value = 40.0
    nt.links.new(tc.outputs["Object"], grit.inputs["Vector"])
    col = nt.nodes.new("ShaderNodeValToRGB")
    col.color_ramp.elements[0].color = lin(pal["background"], 0.25)
    col.color_ramp.elements[1].color = (0.05, 0.05, 0.055, 1)
    nt.links.new(grit.outputs["Fac"], col.inputs["Fac"])
    nt.links.new(col.outputs["Color"], p.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.15
    bump.inputs["Distance"].default_value = 0.004
    nt.links.new(grit.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    return m


def metal():
    m, nt, p = nodes_mat("metal")
    p.inputs["Base Color"].default_value = (0.35, 0.35, 0.36, 1)
    p.inputs["Metallic"].default_value = 1.0
    p.inputs["Roughness"].default_value = 0.35
    return m


def clip(loc, mat):
    x, y, z = loc
    bpy.ops.mesh.primitive_cylinder_add(radius=0.012, depth=0.12, location=(x, (y + WALL_Y) / 2, z),
                                        rotation=(math.radians(90), 0, 0), vertices=12)
    bpy.context.object.data.materials.append(mat)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.024, minor_radius=0.005, location=(x, y, z),
                                     rotation=(math.radians(90), 0, 0))
    bpy.context.object.data.materials.append(mat)


def cable(start, rng, mat):
    x, y, z = start
    cu = bpy.data.curves.new("cable", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth, cu.bevel_resolution = 0.008, 3
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(2)
    pts = [(x, y + 0.04, z), (x + rng.uniform(-0.2, 0.2), WALL_Y - 0.02, z - 0.9), (x + rng.uniform(-0.4, 0.4), -0.25, 0.01)]
    for bp, co in zip(sp.bezier_points, pts):
        bp.co = co
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    ob = bpy.data.objects.new("cable", cu)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)


def glow_lights(pts, color, spacing=0.22, watts=22.0):
    """Small point lights along the tube: the light the gas throws on the wall and the wet floor."""
    acc = 0.0
    prev = Vector(pts[0])
    for p in pts[1:] + pts[:1]:
        p = Vector(p)
        acc += (p - prev).length
        prev = p
        if acc < spacing:
            continue
        acc = 0.0
        ld = bpy.data.lights.new("g", "POINT")
        ld.energy, ld.color, ld.shadow_soft_size = watts, color[:3], 0.03
        ob = bpy.data.objects.new("g", ld)
        bpy.context.collection.objects.link(ob)
        ob.location = p + Vector((0, -0.04, 0))
        ob.visible_camera = False
        ob.visible_glossy = False


def build(name, pal, samples, scale):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene

    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, WALL_Y, 3), rotation=(math.radians(90), 0, 0))
    wall = bpy.context.object
    wall.scale = (24, 6, 1)
    wall.data.materials.append(concrete(pal))
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, -10, 0))
    bpy.context.object.data.materials.append(wet_floor(pal))

    keys = ["accent", "magenta", "cyan", "red", "blue", "yellow"]
    cols = [k for k in keys if isinstance(pal.get(k), str)]
    rng.shuffle(cols)
    cols = ["accent"] + [k for k in cols if k != "accent"][:2]
    order = ["O", "M", "A"]
    rng.shuffle(cols)
    dead = rng.choice(order)
    steel, black = metal(), metal()
    black.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.01, 0.01, 0.01, 1)
    black.node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 0.0
    for key, ck in zip(order, cols):
        color = lin(pal[ck])
        pts = outline(key)
        strength = 0.6 if key == dead else 9.0
        tube(f"{key}-gas", pts, 0.011, gas(color, strength))
        tube(f"{key}-sleeve", pts, 0.024, sleeve_glass(color))
        if key != dead:
            glow_lights(pts, color)
        for i in range(0, len(pts), max(len(pts) // 5, 1)):
            clip(pts[i], steel)
        if key == order[-1]:
            lowest = min(pts, key=lambda p: p[2])
            cable(lowest, rng, black)

    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = lin(pal["background"])
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.05
    sc.world = world

    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = 42
    cam_d.dof.use_dof = True
    cam_d.dof.aperture_fstop = 4.0
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    target = Vector((0, WALL_Y, 0.95))
    side = rng.uniform(-1.6, 1.6)
    cam.location = Vector((side, -8.6, 0.75))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam_d.dof.focus_distance = (Vector((0, WALL_Y - 0.12, Z0)) - cam.location).length
    sc.camera = cam

    r = sc.render
    r.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 10
    sc.cycles.transmission_bounces = 10
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
        out = OUT / f"neon--{name}.png" if args.scale == 100 else ROOT / ".wip" / f"neon--{name}@{args.scale}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        bpy.context.scene.render.filepath = str(out)
        bpy.ops.render.render(write_still=True)
        sign(out, pal, args.scale / 100, f"NEON  ·  {name.upper()}")
        print("wrote", out)


main()
