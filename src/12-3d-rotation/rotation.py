"""12 — 3D Rotation: a specimen chart of the OMA shapes turning through light.

Three rows: O (the circle piece), M (the notched square) and A (the diamond),
built from the exact logo outlines and extruded with soft bevels. Seven columns
step each shape through a rotation, left to right (row O spins on the vertical
axis, M tumbles on the horizontal, A on a diagonal), and every column is a
different optical material: clear glass, dispersive crystal, tinted glass,
chrome, thin-film iridescent, frosted glass and brushed gold. Behind them, thin
glowing lines in the theme's colours make the refraction and reflection visible.

Usage:
  blender -b -P src/12-3d-rotation/rotation.py -- --scheme tokyo-night [--samples 96] [--scale 100]
"""
import argparse
import math
import pathlib
import subprocess
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "palettes"))
sys.path.insert(0, str(ROOT / "src"))
import oma_shapes  # noqa: E402
import palettes  # noqa: E402

SCHEMES = ["tokyo-night", "catppuccin", "gruvbox", "rose-pine", "matte-black"]
OUT = ROOT / "output" / "12-3d-rotation"
COLS = 7
ROW_AXES = {"O": (0, 0, 1), "M": (1, 0, 0), "A": (0.707, 0, 0.707)}
MATERIALS = ["clear glass", "crystal", "tinted glass", "chrome", "iridescent", "frosted", "gold"]


def lin(hex_color, a=1.0):
    def f(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = palettes.rgb(hex_color)
    return (f(r), f(g), f(b), a)


def principled(name, **inputs):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    for k, v in inputs.items():
        key = k.replace("_", " ")
        if key in p.inputs:
            p.inputs[key].default_value = v
    return m


def crystal(name, tint):
    """Glass BSDF with dispersion when this Blender has it, else plain high-IOR glass."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    g = nt.nodes.new("ShaderNodeBsdfGlass")
    g.inputs["Color"].default_value = tint
    g.inputs["IOR"].default_value = 1.75
    g.inputs["Roughness"].default_value = 0.0
    if "Dispersion" in g.inputs:
        g.inputs["Dispersion"].default_value = 0.6
    nt.links.new(g.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m


def make_materials(pal):
    white = (1, 1, 1, 1)
    acc = lin(pal["accent"])
    tint = tuple(0.35 + 0.65 * c for c in acc[:3]) + (1,)
    gold = lin(pal.get("yellow", "#e0af68"))
    return [
        principled("clear", Base_Color=white, Transmission_Weight=1.0, Roughness=0.0, IOR=1.45),
        crystal("crystal", (0.98, 0.98, 1.0, 1)),
        principled("tinted", Base_Color=tint, Transmission_Weight=1.0, Roughness=0.02, IOR=1.52),
        principled("chrome", Base_Color=(0.95, 0.95, 0.97, 1), Metallic=1.0, Roughness=0.03),
        principled("iridescent", Base_Color=(0.9, 0.9, 0.95, 1), Transmission_Weight=1.0, Roughness=0.0,
                   IOR=1.5, Thin_Film_Thickness=520.0, Thin_Film_IOR=1.33),
        principled("frosted", Base_Color=white, Transmission_Weight=1.0, Roughness=0.32, IOR=1.45),
        principled("gold", Base_Color=gold, Metallic=1.0, Roughness=0.22, Anisotropic=0.8),
    ]


def shape(name, poly, depth, mat):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    verts = [bm.verts.new((x, -depth / 2, y)) for x, y in poly]
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
    bev = ob.modifiers.new("bevel", "BEVEL")
    bev.width, bev.segments, bev.limit_method = 0.035, 5, "ANGLE"
    ob.modifiers.new("wn", "WEIGHTED_NORMAL")
    for p in me.polygons:
        p.use_smooth = True
    ob.data.materials.append(mat)
    return ob


def line_backdrop(pal, y=6.0, strength=3.0, camera_visible=True):
    """Plane with thin glowing horizontal lines cycling through the theme colours."""
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, y, 0), rotation=(math.pi / 2, 0, 0))
    plane = bpy.context.object
    m = bpy.data.materials.new("lines")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    out = nt.nodes["Material Output"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    period = 0.45
    scale = nt.nodes.new("ShaderNodeMath"); scale.operation = "DIVIDE"; scale.inputs[1].default_value = period
    frac = nt.nodes.new("ShaderNodeMath"); frac.operation = "FRACT"
    # line mask: narrow band near 0 of each period
    band = nt.nodes.new("ShaderNodeMath"); band.operation = "LESS_THAN"; band.inputs[1].default_value = 0.05
    # colour per line: floor(y/period) mod 5 -> colour ramp
    flo = nt.nodes.new("ShaderNodeMath"); flo.operation = "FLOOR"
    mod = nt.nodes.new("ShaderNodeMath"); mod.operation = "FLOORED_MODULO"; mod.inputs[1].default_value = 5
    div = nt.nodes.new("ShaderNodeMath"); div.operation = "DIVIDE"; div.inputs[1].default_value = 5
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    cols = [pal["accent"], pal.get("magenta", pal["accent"]), pal.get("cyan", pal["accent"]),
            pal.get("yellow", pal["accent"]), pal.get("blue", pal["accent"])]
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, lin(cols[0])
    els[1].position, els[1].color = 0.2, lin(cols[1])
    for i, c in enumerate(cols[2:], start=2):
        e = els.new(i / 5)
        e.color = lin(c)
    emit = nt.nodes.new("ShaderNodeEmission")
    gain = nt.nodes.new("ShaderNodeMath"); gain.operation = "MULTIPLY"; gain.inputs[1].default_value = strength
    base = nt.nodes.new("ShaderNodeBsdfDiffuse")
    base.inputs["Color"].default_value = lin(pal["background"])
    add = nt.nodes.new("ShaderNodeAddShader")
    L = nt.links.new
    L(coord.outputs["Object"], sep.inputs[0])
    L(sep.outputs["Y"], scale.inputs[0])
    L(scale.outputs[0], frac.inputs[0])
    L(frac.outputs[0], band.inputs[0])
    L(scale.outputs[0], flo.inputs[0])
    L(flo.outputs[0], mod.inputs[0])
    L(mod.outputs[0], div.inputs[0])
    L(div.outputs[0], ramp.inputs["Fac"])
    L(ramp.outputs["Color"], emit.inputs["Color"])
    L(band.outputs[0], gain.inputs[0])
    L(gain.outputs[0], emit.inputs["Strength"])
    L(base.outputs[0], add.inputs[0])
    L(emit.outputs[0], add.inputs[1])
    L(add.outputs[0], out.inputs["Surface"])
    plane.data.materials.append(m)
    plane.visible_camera = camera_visible
    return plane


def build(name, pal, samples, scale):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    mats = make_materials(pal)

    col_w, row_h, size = 2.05, 1.95, 1.45
    for r, key in enumerate("OMA"):
        poly = oma_shapes.normalized(oma_shapes.PIECES[key](), size)
        axis = Vector(ROW_AXES[key]).normalized()
        for cidx in range(COLS):
            ob = shape(f"{key}{cidx}", poly, 0.42, mats[cidx])
            angle = math.radians(cidx * 180 / (COLS - 1))
            ob.matrix_world = (Matrix.Translation(((cidx - (COLS - 1) / 2) * col_w, 0, (1 - r) * row_h))
                               @ Matrix.Rotation(angle, 4, axis))

    line_backdrop(pal)
    line_backdrop(pal, y=-9.0, strength=2.0, camera_visible=False)  # seen only in reflections

    def area(nm, loc, rot, energy, size, color=(1, 1, 1)):
        ld = bpy.data.lights.new(nm, "AREA")
        ld.energy, ld.size, ld.color = energy, size, color
        ob = bpy.data.objects.new(nm, ld)
        ob.location, ob.rotation_euler = loc, rot
        sc.collection.objects.link(ob)

    area("key", (-6, -8, 7), (math.radians(55), 0, math.radians(-35)), 1200, 9)
    area("rim", (7, 3, 4), (math.radians(90), 0, math.radians(115)), 800, 3, lin(pal["accent"])[:3])
    area("under", (0, -6, -5), (math.radians(130), 0, 0), 300, 10)

    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = lin(pal["background"])
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    sc.world = world

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 16.2
    cam = bpy.data.objects.new("cam", cam_data)
    cam.location = (0, -20, 0.15)
    cam.rotation_euler = (math.pi / 2, 0, 0)
    sc.collection.objects.link(cam)
    sc.camera = cam

    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 16
    sc.cycles.transmission_bounces = 16
    sc.cycles.glossy_bounces = 8
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.render.resolution_x, sc.render.resolution_y = 3840, 2160
    sc.render.resolution_percentage = scale
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass


def label(path, name, pal, scale):
    """Column captions (rotation + material) and the Omarchy wordmark, via ImageMagick."""
    s = scale / 100
    font = str(ROOT / "assets/fonts/SpaceMono/SpaceMonoNerdFontMono-Regular.ttf")
    dim = pal.get("dark_foreground", pal["foreground"])
    w = 3840 * s
    cmd = ["magick", path, "-font", font, "-fill", dim, "-pointsize", str(max(int(22 * s), 6)),
           "-gravity", "northwest"]
    col_px = 2.05 / 16.2 * w
    for c in range(COLS):
        x = w / 2 + (c - (COLS - 1) / 2) * col_px
        txt = f"{int(c * 180 / (COLS - 1))}°  {MATERIALS[c]}"
        cmd += ["-annotate", f"+{int(x - len(txt) * 6.5 * s)}+{int(2160 * s - 120 * s)}", txt]
    wm = str(ROOT / "assets/brand/omarchy-wordmark.png")
    cmd += ["(", wm, "-alpha", "extract", "-resize", f"{int(360 * s)}x", "-background", pal["accent"],
            "-alpha", "shape", ")", "-gravity", "northwest", "-geometry", f"+{int(90 * s)}+{int(80 * s)}",
            "-composite", path]
    subprocess.run(cmd, check=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheme", default="all")
    ap.add_argument("--samples", type=int, default=96)
    ap.add_argument("--scale", type=int, default=100)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    pals = palettes.load()
    OUT.mkdir(parents=True, exist_ok=True)
    for nm in (SCHEMES if args.scheme == "all" else [args.scheme]):
        build(nm, pals[nm], args.samples, args.scale)
        path = args.out or str(OUT / f"rotation--{nm}.png")
        bpy.context.scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        label(path, nm, pals[nm], args.scale)
        print(f"[rotation] wrote {path}", flush=True)


main()
