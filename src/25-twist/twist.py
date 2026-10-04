"""25 — Twist: variations on the user's twisted wordmark, assets/OMA_01.blend.

The file holds the Omarchy wordmark as an imported-SVG mesh. Solidify gives it
thickness, SimpleDeform twists it about 126° along its length, LaplacianSmooth
softens it, and it is tilted about 42°. The wordmark SVG is built from horizontal
pixel strips, so the twist fans every letter out into spiralling slats. The
object, its modifiers and the camera position are kept. Only the depth-of-field
focus moves (from the now-hidden O onto the wordmark), and each variant swaps
materials, backdrop and lights in Cycles:

  glass      crystal wordmark on black with green rim lights running along the slats
  neon       the slats glow in the OMA logo greens (light -> dark along the word) over a glossy floor
  shadows    matte white wordmark, one low hard light: the slats throw a twisted striped shadow on a wall

Usage:
  blender -b assets/OMA_01.blend -P src/25-twist/twist.py -- --variant glass [--samples 64] [--scale 100]
  blender -b assets/OMA_01.blend -P src/25-twist/twist.py -- --variant all
"""
import argparse
import math
import pathlib
import sys

import bpy

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "palettes"))
import palettes  # noqa: E402

OUT = ROOT / "output" / "25-twist"
PAL = palettes.load()["omarchy"]
GREENS = PAL["oma_bands"]                 # light -> dark
WORD = "omarchy"

# File axes: camera at z = -4 looking toward +z, +y up, screen-right = -x.


def lin(hex_color):
    def f(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = palettes.rgb(hex_color)
    return (f(r), f(g), f(b), 1.0)


def new_material(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.bl_idname != "ShaderNodeOutputMaterial":
            nt.nodes.remove(n)
    return m, nt, nt.nodes["Material Output"]


def set_word_material(mat):
    ob = bpy.data.objects[WORD]
    ob.data.materials.clear()
    ob.data.materials.append(mat)


def word_centre():
    ob = bpy.data.objects[WORD]
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    vs = [ob.matrix_world @ v.co for v in me.vertices]
    return [(min(v[i] for v in vs) + max(v[i] for v in vs)) / 2 for i in range(3)]


def focus_on_word(fstop):
    cam = bpy.context.scene.camera.data
    cam.dof.use_dof = True
    cam.dof.focus_object = None
    c = word_centre()
    cam_pos = bpy.context.scene.camera.location
    cam.dof.focus_distance = math.dist(c, cam_pos)
    cam.dof.aperture_fstop = fstop


def plane(name, loc, rot, size, mat):
    bpy.ops.mesh.primitive_plane_add(size=size, location=loc, rotation=rot)
    ob = bpy.context.object
    ob.name = name
    ob.data.materials.append(mat)
    return ob


def area(name, loc, target, energy, size, color=(1, 1, 1), spec_only=False):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy, ld.color, ld.size = energy, color[:3], size
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    t = bpy.data.objects.new(name + "_t", None)
    bpy.context.scene.collection.objects.link(t)
    t.location = target
    ob.constraints.new("TRACK_TO").target = t
    ob.visible_camera = False
    if spec_only:
        ob.visible_diffuse = False
    return ob


def world(hex_color, strength):
    w = bpy.context.scene.world
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = lin(hex_color)
    bg.inputs["Strength"].default_value = strength


def glow_wall(centre, hex_color, strength, radius):
    """Near-black diffuse wall with a soft radial emission glow centred behind `centre`."""
    m, nt, out = new_material("glow-wall")
    d = nt.nodes.new("ShaderNodeBsdfDiffuse")
    d.inputs["Color"].default_value = (0.004, 0.004, 0.004, 1)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    dist = nt.nodes.new("ShaderNodeVectorMath")
    dist.operation = "DISTANCE"
    dist.inputs[1].default_value = (centre[0], centre[1], 1.4)
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Max"].default_value = radius
    mr.inputs["To Min"].default_value = 1.0
    mr.inputs["To Max"].default_value = 0.0
    sq = nt.nodes.new("ShaderNodeMath")
    sq.operation = "POWER"
    sq.inputs[1].default_value = 2.0
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = strength
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = lin(hex_color)
    add = nt.nodes.new("ShaderNodeAddShader")
    L = nt.links.new
    L(geo.outputs["Position"], dist.inputs[0])
    L(dist.outputs["Value"], mr.inputs["Value"])
    L(mr.outputs["Result"], sq.inputs[0])
    L(sq.outputs[0], mul.inputs[0])
    L(mul.outputs[0], e.inputs["Strength"])
    L(d.outputs[0], add.inputs[0])
    L(e.outputs[0], add.inputs[1])
    L(add.outputs[0], out.inputs["Surface"])
    return m


def diffuse(name, hex_color):
    m, nt, out = new_material(name)
    d = nt.nodes.new("ShaderNodeBsdfDiffuse")
    d.inputs["Color"].default_value = lin(hex_color)
    nt.links.new(d.outputs[0], out.inputs["Surface"])
    return m


# --- variants ------------------------------------------------------------------------
def glass():
    m, nt, out = new_material("word-glass")
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    p.inputs["Base Color"].default_value = (0.92, 1.0, 0.9, 1)
    p.inputs["Transmission Weight"].default_value = 1.0
    p.inputs["Roughness"].default_value = 0.0
    p.inputs["IOR"].default_value = 1.6
    nt.links.new(p.outputs[0], out.inputs["Surface"])
    set_word_material(m)
    c = word_centre()
    plane("wall", (0, 0, 1.4), (0, 0, 0), 30, glow_wall(c, GREENS[2], 0.35, radius=2.0))
    # rims along the slats: two long strips above/below and a cool kicker
    area("rim-top", (c[0], c[1] + 1.4, c[2] + 0.6), c, 160, 3.0, lin(GREENS[1]), spec_only=True)
    area("rim-low", (c[0] - 0.8, c[1] - 1.2, c[2] + 0.3), c, 120, 3.0, lin(GREENS[2]), spec_only=True)
    area("kick", (c[0] + 1.5, c[1] + 0.2, c[2] - 1.5), c, 80, 1.0, (0.85, 0.9, 1.0), spec_only=True)
    world("#000000", 0.0)
    focus_on_word(1.6)


def neon():
    m, nt, out = new_material("word-neon")
    # emission ramp along the word's length (object X) through the OMA greens
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = -0.65
    mr.inputs["From Max"].default_value = 0.55
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, lin(GREENS[4])
    els[1].position, els[1].color = 1.0, lin(GREENS[2])
    mid = els.new(0.5)
    mid.color = lin(GREENS[3])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.1
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    nt.links.new(sep.outputs["X"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    set_word_material(m)
    c = word_centre()
    floor, fnt, fout = new_material("floor")
    p = fnt.nodes.new("ShaderNodeBsdfPrincipled")
    p.inputs["Base Color"].default_value = lin(PAL["darker_background"])
    p.inputs["Roughness"].default_value = 0.18
    p.inputs["Coat Weight"].default_value = 0.5
    fnt.links.new(p.outputs[0], fout.inputs["Surface"])
    # floor just below the word, receding away from the camera
    plane("floor", (0, c[1] - 0.42, 3), (math.radians(90), 0, 0), 30, floor)
    plane("wall", (0, 0, 2.5), (0, 0, 0), 30, diffuse("wall", PAL["darker_background"]))
    world(PAL["background"], 0.02)
    focus_on_word(2.0)


def shadows():
    set_word_material(diffuse("word-white", "#f2f4ef"))
    c = word_centre()
    plane("wall", (0, 0, 0.85), (0, 0, 0), 30, diffuse("wall", "#e9ede4"))
    # low, hard key from the right and below, raking across the slats onto the wall
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy, sun.angle, sun.color = 4.0, math.radians(0.5), lin(GREENS[0])[:3]
    so = bpy.data.objects.new("sun", sun)
    bpy.context.scene.collection.objects.link(so)
    so.location = (c[0] - 2.6, c[1] - 1.1, c[2] - 2.2)
    t = bpy.data.objects.new("sun_t", None)
    bpy.context.scene.collection.objects.link(t)
    t.location = (c[0] + 0.4, c[1] + 0.25, 0.85)
    so.constraints.new("TRACK_TO").target = t
    area("fill", (0, 1.5, -3.5), c, 40, 6.0, (0.9, 0.95, 1.0))
    world("#dfe4d9", 0.15)
    focus_on_word(2.8)


VARIANTS = {"glass": glass, "neon": neon, "shadows": shadows}


def render_settings(samples, scale):
    sc = bpy.context.scene
    bpy.data.objects["Light"].hide_render = True
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 16
    sc.cycles.transmission_bounces = 16
    sc.cycles.caustics_reflective = sc.cycles.caustics_refractive = False
    sc.render.resolution_x, sc.render.resolution_y = 3840, 2160
    sc.render.resolution_percentage = scale
    sc.view_settings.view_transform = "AgX"


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="all")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--scale", type=int, default=100)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    blend = bpy.data.filepath
    for name in (VARIANTS if args.variant == "all" else [args.variant]):
        bpy.ops.wm.open_mainfile(filepath=blend)          # every variant starts from the untouched file
        VARIANTS[name]()
        render_settings(args.samples, args.scale)
        path = args.out or str(OUT / f"twist--{name}.png")
        bpy.context.scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        print(f"[twist] wrote {path}", flush=True)


main()
