"""01 — Monolith: the OMA logo as a banded 3D sculpture (Blender / Cycles).

The OMA mark (circle + notched square + diamond, 5 horizontal colour bands) is
rebuilt from its SVG geometry, each band sliced into its own extruded slab with
staggered depth, standing on a glossy floor in front of a glowing halo ring.

Usage:
  blender -b -P src/01-monolith/monolith.py -- --scheme tokyo-night [--samples 96] [--scale 100]
  blender -b -P src/01-monolith/monolith.py -- --scheme all
"""
import argparse
import math
import pathlib
import sys

import bmesh
import bpy

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "palettes"))
import palettes  # noqa: E402

SCHEMES = ["tokyo-night", "gruvbox", "ethereal", "osaka-jade", "matte-black"]
OUT = ROOT / "output" / "01-monolith"

# --- OMA logo geometry (SVG units, viewBox 800x800, y down) -----------------
CX, CY, R = 188.0, 400.0, 149.0          # circle the left piece + square bite share
BANDS = [250.0, 328.9, 360.5, 423.7, 471.1, 550.0]  # gradient stop positions


A0 = math.acos((283.0 - CX) / R)  # angle where the circle meets the x=283 chord


def arc(a_from, a_to, steps=72):
    return [(CX + R * math.cos(a_from + (a_to - a_from) * i / steps),
             CY + R * math.sin(a_from + (a_to - a_from) * i / steps)) for i in range(steps + 1)]


def circle_piece():
    """Left piece: the big arc of the circle, closed by the x=283 chord."""
    return arc(A0, 2 * math.pi - A0, 160)


def square_piece():
    """Square with the circle's bulge bitten out of its left side and a V notch on the right."""
    return ([(283.0, 262.0), (536.0, 262.0), (536.0, 326.0), (462.0, 400.0),
             (536.0, 474.0), (536.0, 536.0), (283.0, 536.0)]
            + arc(A0, -A0, 72))


def diamond_piece():
    return [(536.0, 326.0), (610.5, 251.5), (759.0, 400.0), (610.5, 548.5), (536.0, 474.0)]


def clip(poly, y0, y1):
    """Sutherland–Hodgman clip of a polygon to the horizontal slab y0<=y<=y1."""
    def clip_edge(pts, inside, inter):
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(inter(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(inter(prev, cur))
        return out

    def at_y(y):
        def f(a, b):
            t = (y - a[1]) / (b[1] - a[1])
            return (a[0] + t * (b[0] - a[0]), y)
        return f

    pts = clip_edge(poly, lambda p: p[1] >= y0, at_y(y0))
    if pts:
        pts = clip_edge(pts, lambda p: p[1] <= y1, at_y(y1))
    # drop near-duplicate points
    clean = []
    for p in pts:
        if not clean or abs(p[0] - clean[-1][0]) + abs(p[1] - clean[-1][1]) > 1e-3:
            clean.append(p)
    return clean


# --- colour helpers ---------------------------------------------------------
def srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lin(hex_color, a=1.0):
    r, g, b = palettes.rgb(hex_color)
    return (srgb_to_lin(r), srgb_to_lin(g), srgb_to_lin(b), a)


def mix(c1, c2, t):
    return tuple(c1[i] * (1 - t) + c2[i] * t for i in range(4))


# --- scene construction -----------------------------------------------------
def material(name, color, rough=0.25, emit=None, strength=0.0, metallic=0.0, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = color
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metallic
    if "Coat Weight" in p.inputs:
        p.inputs["Coat Weight"].default_value = coat
    if emit is not None:
        p.inputs["Emission Color"].default_value = emit
        p.inputs["Emission Strength"].default_value = strength
    return m


def glow_wall(base, glow, strength=1.6, radius=13.0, center_z=1.8):
    """Matte backdrop with a soft radial accent glow painted behind the logo."""
    m = material("wall", base, rough=0.9, emit=glow, strength=strength)
    nt = m.node_tree
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1 / radius, 1 / radius, 1)
    mapping.inputs["Location"].default_value = (2.5 / radius, -center_z / radius, 0)
    grad = nt.nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "SPHERICAL"
    ramp = nt.nodes.new("ShaderNodeMath")
    ramp.operation = "POWER"
    ramp.inputs[1].default_value = 2.2
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = strength
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], grad.inputs["Vector"])
    nt.links.new(grad.outputs["Fac"], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], mul.inputs[0])
    nt.links.new(mul.outputs[0], nt.nodes["Principled BSDF"].inputs["Emission Strength"])
    return m


def slab(name, poly, depth, y_shift, mat):
    """Extrude a 2D SVG polygon into an upright slab (x right, z up)."""
    s = 0.01  # svg units -> metres
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    verts = [bm.verts.new(((x - 400) * s, y_shift, (550 - y) * s)) for x, y in poly]
    face = bm.faces.new(verts)
    bmesh.ops.recalc_face_normals(bm, faces=[face])
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=moved, vec=(0, depth, 0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)
    bev = ob.modifiers.new("bevel", "BEVEL")
    bev.width = 0.012
    bev.segments = 3
    bev.limit_method = "ANGLE"
    for poly_ in me.polygons:
        poly_.use_smooth = False
    return ob


def build(pal, samples, scale):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene

    bg = lin(pal["background"])
    dark = lin(pal.get("darker_background", pal["background"]))
    fg = lin(pal.get("bright_foreground", pal["foreground"]))
    acc = lin(pal["accent"])
    alt = lin(pal.get("magenta", pal["accent"]))

    # band colours mimic the logo: light -> accent -> deep
    band_cols = [mix(fg, acc, 0.4), mix(fg, acc, 0.7), acc, mix(acc, dark, 0.45), mix(acc, dark, 0.75)]
    gap = 3.0  # svg units between band slabs
    stagger = [0.00, -0.10, -0.22, -0.10, 0.04]

    for bi in range(5):
        y0, y1 = BANDS[bi] + gap / 2, BANDS[bi + 1] - gap / 2
        glow = 0.6 if bi == 2 else 0.0
        mat = material(f"band{bi}", band_cols[bi], rough=0.18 + 0.06 * bi,
                       emit=band_cols[bi], strength=glow, coat=0.6)
        for pi, poly in enumerate((circle_piece(), square_piece(), diamond_piece())):
            part = clip(poly, y0, y1)
            if len(part) >= 3:
                slab(f"p{pi}b{bi}", part, 0.55, stagger[bi] + 0.06 * (pi - 1), mat)

    # glossy floor
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 0, 0))
    bpy.context.object.data.materials.append(material("floor", mix(dark, bg, 0.3), rough=0.12))

    # halo ring behind the logo
    bpy.ops.mesh.primitive_torus_add(major_radius=2.5, minor_radius=0.03, location=(-0.1, 3.0, 1.5),
                                     rotation=(math.pi / 2, 0, 0), major_segments=256)
    bpy.context.object.data.materials.append(material("halo", acc, emit=acc, strength=30.0))
    bpy.ops.mesh.primitive_torus_add(major_radius=3.9, minor_radius=0.012, location=(-0.1, 5.5, 1.5),
                                     rotation=(math.pi / 2, 0, 0), major_segments=256)
    bpy.context.object.data.materials.append(material("halo2", alt, emit=alt, strength=10.0))

    # backdrop wall
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 14, 0), rotation=(math.pi / 2, 0, 0))
    bpy.context.object.data.materials.append(glow_wall(bg, mix(acc, bg, 0.35)))

    # lights
    def area(name, loc, rot, color, energy, size, glossy=True):
        ld = bpy.data.lights.new(name, "AREA")
        ld.color = color[:3]
        ld.energy = energy
        ld.size = size
        ob = bpy.data.objects.new(name, ld)
        ob.location, ob.rotation_euler = loc, rot
        ob.visible_glossy = glossy
        sc.collection.objects.link(ob)

    area("key", (-5, -6, 7), (math.radians(55), 0, math.radians(-38)), fg, 650, 6, glossy=False)
    area("fill", (2, -12, 2.5), (math.radians(85), 0, math.radians(10)), fg, 220, 8, glossy=False)
    area("rim_l", (-6, 3, 3), (math.radians(90), 0, math.radians(-120)), acc, 1400, 1.2)
    area("rim_r", (6, 3, 3), (math.radians(90), 0, math.radians(120)), alt, 1100, 1.2)
    area("top", (0, 1, 9), (0, 0, 0), fg, 250, 10)

    # world
    world = bpy.data.worlds.new("world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = bg
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.4
    sc.world = world

    # camera
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 42
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = 4.0
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    cam.location = (3.6, -17.5, 1.0)
    target = bpy.data.objects.new("target", None)
    target.location = (-0.1, 0, 1.9)
    sc.collection.objects.link(target)
    con = cam.constraints.new("TRACK_TO")
    con.target = target
    cam_data.dof.focus_object = target
    sc.camera = cam

    # render settings
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 6
    sc.render.resolution_x, sc.render.resolution_y = 3840, 2160
    sc.render.resolution_percentage = scale
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_depth = "8"
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    sc.render.film_transparent = False


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheme", default="all")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--scale", type=int, default=100)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    pals = palettes.load()
    names = SCHEMES if args.scheme == "all" else [args.scheme]
    OUT.mkdir(parents=True, exist_ok=True)
    for name in names:
        build(pals[name], args.samples, args.scale)
        path = args.out or str(OUT / f"monolith--{name}.png")
        bpy.context.scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        print(f"[monolith] wrote {path}")


main()
