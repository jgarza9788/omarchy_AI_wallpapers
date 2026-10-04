"""23a — OMA Icon Wall: the OMA from assets/OMA.blend in glass, lit by a wall of glowing app icons.

Works inside the user's file: it opens assets/OMA.blend and keeps its camera, its
framing, and the O / M / A column (top to bottom) exactly as modelled. It:
  * removes the Array modifiers so there's one OMA, and keeps the Boolean notch on the M
  * gives the three pieces crystal glass with a small bevel so the edges catch light
  * fills the wall behind them with a grid of emissive Nerd Font icons, the only real light
    in the scene, so the glass refracts and reflects real icons
  * adds softboxes that light specular highlights only (no diffuse spill)

File axes: the camera sits at z = -4 looking toward +z, +y is up and screen-right is -x.

Usage:
  blender -b assets/OMA.blend -P src/23-oma-blend/oma_icon_wall.py -- --scheme omarchy [--samples 64] [--scale 100]
"""
import argparse
import hashlib
import math
import pathlib
import random
import sys

import bpy

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "palettes"))
import palettes  # noqa: E402

FONT = ROOT / "assets" / "fonts" / "Iosevka" / "IosevkaNerdFontMono-Regular.ttf"
OUT = ROOT / "output" / "23-oma-blend"
PIECES = {"O": "Cylinder", "M": "Cube.002", "A": "Cube.001"}
ICONS = [0xF303, 0xF17C, 0xF359, 0xF489, 0xF120, 0xF269, 0xF268, 0xE7C5, 0xF338, 0xE795, 0xF308, 0xE73C,
         0xE739, 0xE791, 0xF1BC, 0xF167, 0xE60B, 0xF0E0, 0xF1C0, 0xE706, 0xE7B1, 0xF07B, 0xF015, 0xF001,
         0xF03D, 0xF030, 0xF11B, 0xF1FC, 0xF0AD, 0xF121, 0xF126, 0xF09B, 0xF113, 0xF2DC, 0xF0C2, 0xF1EB,
         0xE702, 0xF418, 0xE62B, 0xE7A8, 0xE627, 0xE74E, 0xE620, 0xE718, 0xF013, 0xF233, 0xE615, 0xE737]

WALL_Z = 0.7         # icon wall distance behind the OMA (the OMA sits at z = 0)
PITCH = 0.2          # icon grid spacing (m)
TURN = 30            # whole-column rotation about the vertical axis (deg): shows the side faces
TILT = 8             # slight lean toward the camera (deg)


def lin(hex_color):
    def f(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = palettes.rgb(hex_color)
    return (f(r), f(g), f(b), 1.0)


def principled(name, **inputs):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    for k, v in inputs.items():
        p.inputs[k.replace("_", " ")].default_value = v
    return m


def emission(name, color, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = color
    e.inputs["Strength"].default_value = strength
    nt.links.new(e.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m


def prepare_oma(glass):
    # one pivot for the whole column, so turning it keeps the O / M / A order and spacing
    pivot = bpy.data.objects.new("OMA", None)
    bpy.context.scene.collection.objects.link(pivot)
    pivot.location = (0, -0.02, 0)
    for key, name in PIECES.items():
        ob = bpy.data.objects[name]
        mw = ob.matrix_world.copy()
        ob.parent = pivot
        ob.matrix_world = mw
        for m in list(ob.modifiers):
            if m.type == "NODES":          # the Array modifiers -> a single OMA
                ob.modifiers.remove(m)
        bev = ob.modifiers.new("bevel", "BEVEL")
        bev.width, bev.segments, bev.limit_method = 0.008, 4, "ANGLE"
        ob.data.materials.clear()
        ob.data.materials.append(glass)
        for p in ob.data.polygons:
            p.use_smooth = False
    # the Boolean cutter must follow the M
    cutter = bpy.data.objects["Cube.003"]
    mw = cutter.matrix_world.copy()
    cutter.parent = pivot
    cutter.matrix_world = mw
    pivot.rotation_euler = (math.radians(TILT), math.radians(TURN), 0)


def icon_wall(pal, rng, strength):
    font = bpy.data.fonts.load(str(FONT), check_existing=True)
    if "oma_bands" in pal:      # official palette: the OMA logo's greens + the foreground
        colours = pal["oma_bands"][:4] + [pal["foreground"]]
    else:
        colours = [pal[k] for k in ("accent", "blue", "cyan", "magenta", "green", "yellow") if k in pal]
    mats = [emission(f"glow{i}", lin(c), strength) for i, c in enumerate(colours)]
    cols, rows = 24, 14
    for i in range(cols):
        for j in range(rows):
            cu = bpy.data.curves.new(f"icon{i}_{j}", "FONT")
            cu.font = font
            cu.body = chr(ICONS[rng.randrange(len(ICONS))])
            cu.align_x, cu.align_y = "CENTER", "CENTER"
            cu.size = PITCH * 0.62
            ob = bpy.data.objects.new(cu.name, cu)
            bpy.context.scene.collection.objects.link(ob)
            ob.location = ((i - (cols - 1) / 2) * PITCH, (j - (rows - 1) / 2) * PITCH, WALL_Z)
            ob.rotation_euler = (0, math.pi, 0)          # face the camera (which looks toward +z) and read correctly
            cu.materials.append(mats[rng.randrange(len(mats))])


def backdrop(pal):
    """Purely diffuse (no specular) dark wall: it can't pick up the softbox highlights."""
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, WALL_Z + 0.01))
    m = bpy.data.materials.new("wall")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    d = nt.nodes.new("ShaderNodeBsdfDiffuse")
    d.inputs["Color"].default_value = lin(pal.get("darker_background", pal["background"]))
    # a soft accent glow centred behind the column, so the glass silhouettes read against it
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = lin(pal["accent"])
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / 1.1, 1 / 1.4, 1)
    gr = nt.nodes.new("ShaderNodeTexGradient")
    gr.gradient_type = "SPHERICAL"
    pw = nt.nodes.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = 2.0
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = 0.35
    add = nt.nodes.new("ShaderNodeAddShader")
    L = nt.links.new
    L(tc.outputs["Object"], mp.inputs["Vector"])
    L(mp.outputs["Vector"], gr.inputs["Vector"])
    L(gr.outputs["Fac"], pw.inputs[0])
    L(pw.outputs[0], mul.inputs[0])
    L(mul.outputs[0], e.inputs["Strength"])
    L(d.outputs[0], add.inputs[0])
    L(e.outputs[0], add.inputs[1])
    L(add.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    bpy.context.object.data.materials.append(m)


def softbox(name, loc, energy, size, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy, ld.size, ld.color = energy, size, color[:3]
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (0, 0, 0)
    tgt = bpy.data.objects.new(name + "_t", None)
    bpy.context.scene.collection.objects.link(tgt)
    ob.constraints.new("TRACK_TO").target = tgt
    ob.visible_camera = False
    ob.visible_diffuse = False          # highlights on glass only; the room stays dark
    return ob


def build(name, pal, samples, scale):
    rng = random.Random(int(hashlib.sha256(name.encode()).hexdigest()[:8], 16))
    sc = bpy.context.scene
    bpy.data.objects["Light"].hide_render = True          # the icons are the light
    glass = principled("crystal", Base_Color=(0.95, 0.98, 1.0, 1), Transmission_Weight=1.0, Roughness=0.0, IOR=1.6)
    prepare_oma(glass)
    icon_wall(pal, rng, strength=8.0)
    backdrop(pal)
    softbox("key", (1.6, 1.6, -2.5), 350, 4.0)
    softbox("top", (0.0, 3.0, -0.5), 250, 4.0)
    softbox("rim", (-1.8, -0.4, -1.2), 200, 3.0, lin(pal["accent"]))
    w = sc.world
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = lin(pal["background"])
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.02

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
    ap.add_argument("--scheme", default="omarchy")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--scale", type=int, default=100)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    pal = palettes.load()[args.scheme]
    build(args.scheme, pal, args.samples, args.scale)
    path = args.out or str(OUT / f"oma-icon-wall--{args.scheme}.png")
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print(f"[oma-icon-wall] wrote {path}", flush=True)


main()
