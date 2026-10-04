"""15.1 — Wake: the interceptor sprite (Blender/Cycles, transparent PNG).

An original sci-fi interceptor built procedurally: a lofted fuselage with a
needle nose, swept delta wings with cranked tips, twin engine nacelles with
glowing bells, canted tail fins, a glass canopy and accent running lights.
Rendered orthographically from above-front with the nose pointing screen-right,
banked a little so it reads as 3D. Next to the PNG it writes <out>.json with the
sprite-pixel positions of the nose and the engine exhausts (for the jets).

Usage: blender -b -P src/15.1-wake/ship.py -- --scheme omarchy [--samples 64] [--size 1400] [--out .wip/ship/ship--omarchy.png]
"""
import argparse
import json
import math
import pathlib
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "palettes"))
import palettes  # noqa: E402


def lin(hex_color, k=1.0):
    def f(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = palettes.rgb(hex_color)
    return (f(r) * k, f(g) * k, f(b) * k, 1.0)


def mix(a, b, t):
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3)) + (1.0,)


def mesh_obj(name, verts, faces, mat, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = smooth
    return ob


def loft(name, sections, mat, n=32, y0=0.0):
    """Closed tube through elliptical sections (x, half-width, half-height, z-offset), capped."""
    verts, faces = [], []
    for x, ry, rz, zo in sections:
        for k in range(n):
            a = 2 * math.pi * k / n
            # squarish ellipse (superellipse) reads as an armoured hull, not a sausage
            c, s = math.cos(a), math.sin(a)
            e = 0.7
            verts.append((x, y0 + ry * math.copysign(abs(c) ** e, c), zo + rz * math.copysign(abs(s) ** e, s)))
    m = len(sections)
    for i in range(m - 1):
        for k in range(n):
            a, b = i * n + k, i * n + (k + 1) % n
            faces.append((a, b, b + n, a + n))
    verts.append((sections[0][0], y0, sections[0][3]))
    verts.append((sections[-1][0], y0, sections[-1][3]))
    c0, c1 = len(verts) - 2, len(verts) - 1
    for k in range(n):
        faces.append((c0, (k + 1) % n, k))
        faces.append((c1, (m - 1) * n + k, (m - 1) * n + (k + 1) % n))
    return mesh_obj(name, verts, faces, mat)


def slab(name, outline, z, t, mat):
    """Extrude a planar outline [(x, y)] into a thin plate centred at height z."""
    n = len(outline)
    verts = [(x, y, z + t / 2) for x, y in outline] + [(x, y, z - t / 2) for x, y in outline]
    faces = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    faces += [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
    ob = mesh_obj(name, verts, faces, mat, smooth=False)
    bev = ob.modifiers.new("bevel", "BEVEL")
    bev.width, bev.segments = t * 0.45, 3
    return ob


def material(name, color, metallic=0.0, rough=0.4, emit=None, strength=1.0, glass=False, panels=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = color
    p.inputs["Metallic"].default_value = metallic
    p.inputs["Roughness"].default_value = rough
    if glass:
        p.inputs["Transmission Weight"].default_value = 1.0
        p.inputs["IOR"].default_value = 1.45
        p.inputs["Roughness"].default_value = 0.05
    if emit is not None:
        p.inputs["Emission Color"].default_value = emit
        p.inputs["Emission Strength"].default_value = strength
    if panels:   # panel seams: a brick texture drives a darker base and a bump
        tc = nt.nodes.new("ShaderNodeTexCoord")
        br = nt.nodes.new("ShaderNodeTexBrick")
        br.inputs["Scale"].default_value = 7.0
        br.inputs["Mortar Size"].default_value = 0.01
        br.inputs["Color1"].default_value = color
        br.inputs["Color2"].default_value = mix(color, (0, 0, 0), 0.08)
        br.inputs["Mortar"].default_value = mix(color, (0, 0, 0), 0.55)
        nt.links.new(tc.outputs["Object"], br.inputs["Vector"])
        nt.links.new(br.outputs["Color"], p.inputs["Base Color"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.2
        bump.inputs["Distance"].default_value = 0.02
        nt.links.new(br.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    return m


def area(name, loc, target, size, energy, color=(1, 1, 1), diffuse=True):
    ld = bpy.data.lights.new(name, "AREA")
    ld.size, ld.energy, ld.color = size, energy, color
    ob = bpy.data.objects.new(name, ld)
    bpy.context.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    ob.visible_diffuse = diffuse
    return ob


def build(pal):
    fg = lin(pal["foreground"])
    dfg = lin(pal.get("dark_foreground", pal["foreground"]))
    hull_c = mix(fg, dfg, 0.35)
    dark_c = mix(lin(pal.get("darker_background", pal["background"])), dfg, 0.25)
    accent = lin(pal["accent"])
    hot = lin(pal.get("bright_foreground", pal["foreground"]))

    hull = material("hull", hull_c, metallic=0.85, rough=0.32, panels=True)
    dark = material("dark", dark_c, metallic=0.6, rough=0.45)
    glass = material("glass", mix(dark_c, accent, 0.25), rough=0.06, emit=accent, strength=0.04)
    trim = material("trim", accent, emit=accent, strength=1.2)
    engine = material("engine", hot, emit=mix(hot, accent, 0.35), strength=4.0)

    parts = []
    # fuselage: needle nose -> cockpit hump -> broad body -> tapered tail
    parts.append(loft("fuselage", [
        (3.0, 0.01, 0.01, 0.02), (2.6, 0.10, 0.07, 0.03), (2.0, 0.24, 0.15, 0.05),
        (1.2, 0.38, 0.24, 0.07), (0.3, 0.50, 0.30, 0.06), (-0.8, 0.55, 0.28, 0.04),
        (-1.8, 0.46, 0.22, 0.02), (-2.4, 0.32, 0.16, 0.0)], hull))
    # canopy: a long glass teardrop over the hump
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, location=(1.0, 0, 0.26))
    can = bpy.context.object
    can.scale = (0.85, 0.2, 0.16)
    can.data.materials.append(glass)
    bpy.ops.object.shade_smooth()
    parts.append(can)
    # swept delta wings with cranked tips
    for side in (1, -1):
        wing = [(1.2, 0.35), (-0.4, 1.6), (-1.1, 2.45), (-1.55, 2.5), (-1.45, 1.7), (-2.0, 0.9), (-1.9, 0.35)]
        parts.append(slab(f"wing{side}", [(x, y * side) for x, y in (wing if side > 0 else wing[::-1])],
                          -0.02, 0.09, hull))
        # leading-edge accent strip + wingtip running light
        parts.append(slab(f"edge{side}", [(x, y * side) for x, y in
                     ([(1.1, 0.40), (-1.08, 2.44), (-1.11, 2.40), (1.04, 0.40)] if side > 0 else
                      [(1.04, 0.40), (-1.11, 2.40), (-1.08, 2.44), (1.1, 0.40)])], 0.035, 0.02, trim))
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.07, location=(-1.35, 2.47 * side, 0.0))
        bpy.context.object.data.materials.append(trim)
        # nacelle + glowing bell + canted fin
        y = 0.82 * side
        parts.append(loft(f"nacelle{side}", [
            (0.4, 0.02, 0.02, 0.0), (0.2, 0.15, 0.13, 0.0), (-0.4, 0.24, 0.21, 0.0),
            (-2.2, 0.24, 0.21, 0.0), (-2.45, 0.2, 0.18, 0.0)], dark, y0=y))
        bpy.ops.mesh.primitive_cylinder_add(radius=0.17, depth=0.06, location=(-2.47, y, 0.0),
                                            rotation=(0, math.pi / 2, 0))
        bpy.context.object.data.materials.append(engine)
        parts.append(slab(f"stripe{side}", [(-0.3, y + 0.03), (-2.2, y + 0.03), (-2.2, y - 0.03), (-0.3, y - 0.03)],
                          0.215, 0.012, trim))
        fin_o = [(-1.4, 0.0), (-2.3, 0.0), (-2.5, 0.75), (-2.1, 0.75)]
        fin = slab(f"fin{side}", [(x, v * side) for x, v in (fin_o if side > 0 else fin_o[::-1])], 0.0, 0.06, hull)
        fin.rotation_euler = (math.radians(90 - 22) * side, 0, 0)
        fin.location = (0, y, 0.15)
    return {"nose": (3.0, 0, 0.02), "engines": [(-2.5, 0.82, 0.0), (-2.5, -0.82, 0.0)]}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheme", default="omarchy")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--size", type=int, default=1400)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    pal = palettes.load()[args.scheme]
    out = pathlib.Path(args.out or ROOT / ".wip" / "ship" / f"ship--{args.scheme}.png")
    out.parent.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    marks = build(pal)

    # a slight bank toward the camera: parent everything to one pivot
    pivot = bpy.data.objects.new("pivot", None)
    sc.collection.objects.link(pivot)
    for ob in list(sc.objects):
        if ob is not pivot:
            ob.parent = pivot
    pivot.rotation_euler = (math.radians(12), 0, 0)
    bpy.context.view_layer.update()

    cam_d = bpy.data.cameras.new("cam")
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = 7.4
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    elev = math.radians(36)
    cam.location = (0, -12 * math.cos(elev), 12 * math.sin(elev))
    cam.rotation_euler = (Vector((0, 0, 0)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam

    accent = lin(pal["accent"])[:3]
    area("key", (3, -5, 7), (0, 0, 0), 5, 1500)
    area("rim", (-6, 5, 2), (0, 0, 0), 4, 700, color=accent)
    area("fill", (2, -6, -1), (0, 0, 0), 6, 150, color=lin(pal.get("blue", pal["accent"]))[:3])
    area("soft", (0.5, -3, 6), (0.5, 0, 0), 3, 600, diffuse=False)   # specular-only: gives the canopy a highlight

    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = lin(pal["background"])
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    sc.world = world

    r = sc.render
    r.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = args.samples
    sc.cycles.use_denoising = True
    r.film_transparent = True
    r.resolution_x, r.resolution_y = args.size, int(args.size * 0.62)
    r.resolution_percentage = 100
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGBA"
    sc.view_settings.view_transform = "AgX"
    r.filepath = str(out)
    bpy.ops.render.render(write_still=True)

    def px(p):
        v = world_to_camera_view(sc, cam, pivot.matrix_world @ Vector(p))
        return [v.x * r.resolution_x, (1 - v.y) * r.resolution_y]
    meta = {"size": [r.resolution_x, r.resolution_y], "nose": px(marks["nose"]),
            "engines": [px(e) for e in marks["engines"]], "tail": px((-2.5, 0, 0))}
    out.with_suffix(".json").write_text(json.dumps(meta))
    print("wrote", out)


main()
