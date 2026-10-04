"""24 — OMA Dome: variations on the user's own scene, assets/OMA_00.blend.

The file holds a 3-row grid: O on top, M in the middle, A at the bottom. Each row
is arrayed into columns that turn from left to right and soften into a blur on
the right. Behind it sits a huge mirror sphere (the "dome"). The scene was built
for EEVEE, whose Specular shader renders black in Cycles and whose glass shows
dark grey. This script keeps the geometry, the Array grid, the camera and the
blur fade untouched. It only re-lights the scene for Cycles, so the glass truly
refracts, swapping the dome's material, the glass and the lights per variant:

  greenhouse  the dome glows in the Omarchy greens, brightest behind the grid
  icon-dome   the dome is tiled with glowing Nerd Font app icons (icons.png on its UVs)
  mirror      the file's own green mirror sphere, ported to Cycles, reflecting a soft green sky
  long-shadow a matte white dome and one low, hard green spot: long crisp shadows across the wall

Usage:
  blender -b assets/OMA_00.blend -P src/24-oma-dome/oma_dome.py -- --variant greenhouse [--samples 64] [--scale 100]
  blender -b assets/OMA_00.blend -P src/24-oma-dome/oma_dome.py -- --variant all
"""
import argparse
import pathlib
import sys

import bpy

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "palettes"))
import palettes  # noqa: E402

OUT = ROOT / "output" / "24-oma-dome"
PIECES = ["Cylinder", "Cube.002", "Cube.001"]      # O, M, A
PAL = palettes.load()["omarchy"]
GREENS = PAL["oma_bands"]                         # light -> dark


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


def facing(nt):
    """1 where the dome faces the camera, falling to 0 at its silhouette."""
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    inv = nt.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    nt.links.new(lw.outputs["Facing"], inv.inputs[1])
    return inv.outputs[0]


def set_dome(mat):
    dome = bpy.data.objects["Sphere"]
    dome.data.materials.clear()
    dome.data.materials.append(mat)


def set_glass(mat):
    for n in PIECES:
        ob = bpy.data.objects[n]
        ob.data.materials.clear()
        ob.data.materials.append(mat)


def glass(name="glass", thin_film=0.0, tint=(1, 1, 1, 1), ior=1.5):
    m, nt, out = new_material(name)
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    p.inputs["Base Color"].default_value = tint
    p.inputs["Transmission Weight"].default_value = 1.0
    p.inputs["Roughness"].default_value = 0.0
    p.inputs["IOR"].default_value = ior
    if thin_film:
        p.inputs["Thin Film Thickness"].default_value = thin_film
        p.inputs["Thin Film IOR"].default_value = 1.33
    nt.links.new(p.outputs[0], out.inputs["Surface"])
    return m


# --- variants -------------------------------------------------------------------------
def greenhouse():
    m, nt, out = new_material("dome-greenhouse")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (0.0, 0.0, 0.0, 1)
    els[1].position, els[1].color = 1.0, lin(GREENS[2])
    mid = els.new(0.5)
    mid.color = lin(GREENS[4])
    # radial glow: 1 at a point on the dome behind the grid, fading out over ~1.3 m (the visible patch)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    dist = nt.nodes.new("ShaderNodeVectorMath")
    dist.operation = "DISTANCE"
    dist.inputs[1].default_value = (0.5, 0.0, 0.6)      # screen-right is -x in this file: +x keeps it behind the grid
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = 0.0
    mr.inputs["From Max"].default_value = 2.4
    mr.inputs["To Min"].default_value = 1.0
    mr.inputs["To Max"].default_value = 0.0
    nt.links.new(geo.outputs["Position"], dist.inputs[0])
    nt.links.new(dist.outputs["Value"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.6
    nt.links.new(ramp.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    set_dome(m)
    set_glass(glass(tint=(0.96, 1.0, 0.96, 1)))
    world(PAL["darker_background"], 0.0)


def icon_dome():
    m, nt, out = new_material("dome-icons")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(HERE / "icons.png"))
    tex.interpolation = "Cubic"
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (3.0, 3.0, 1)        # more, smaller icons across the dome
    uv = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(uv.outputs["UV"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
    # icon colour varies across the dome through the OMA greens
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.35, lin(GREENS[2])
    els[1].position, els[1].color = 0.65, lin(GREENS[0])
    nt.links.new(uv.outputs["UV"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(ramp.outputs["Color"], em.inputs["Color"])
    strength = nt.nodes.new("ShaderNodeMath")
    strength.operation = "MULTIPLY"
    nt.links.new(tex.outputs["Color"], strength.inputs[0])
    nt.links.new(facing(nt), strength.inputs[1])            # fade icons toward the dome's edge
    gain = nt.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY"
    gain.inputs[1].default_value = 4.0
    nt.links.new(strength.outputs[0], gain.inputs[0])
    # per-region brightness variation so the bokeh orbs don't all look alike
    vary = nt.nodes.new("ShaderNodeTexNoise")
    vary.inputs["Scale"].default_value = 70.0
    vmul = nt.nodes.new("ShaderNodeMath")
    vmul.operation = "MULTIPLY"
    punch = nt.nodes.new("ShaderNodeMapRange")       # stretch the noise: many dark, a few hot
    punch.inputs["From Min"].default_value = 0.42
    punch.inputs["From Max"].default_value = 0.62
    punch.inputs["To Min"].default_value = 0.02
    punch.inputs["To Max"].default_value = 1.6
    nt.links.new(uv.outputs["UV"], vary.inputs["Vector"])
    nt.links.new(vary.outputs["Fac"], punch.inputs["Value"])
    nt.links.new(gain.outputs[0], vmul.inputs[0])
    nt.links.new(punch.outputs["Result"], vmul.inputs[1])
    gain = vmul
    nt.links.new(gain.outputs[0], em.inputs["Strength"])
    dark = nt.nodes.new("ShaderNodeBsdfDiffuse")
    dark.inputs["Color"].default_value = lin(PAL["darker_background"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(dark.outputs[0], add.inputs[0])
    nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    set_dome(m)
    set_glass(glass(ior=1.6))
    world(PAL["darker_background"], 0.0)


def mirror():
    """The user's original EEVEE look, ported to Cycles: a green mirror sphere behind clear glass."""
    m, nt, out = new_material("dome-mirror")
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    p.inputs["Base Color"].default_value = (0.0, 0.8, 0.028, 1)     # the file's own green
    p.inputs["Metallic"].default_value = 1.0
    p.inputs["Roughness"].default_value = 0.0
    nt.links.new(p.outputs[0], out.inputs["Surface"])
    set_dome(m)
    set_glass(glass())
    # something bright for the mirror to reflect: a soft gradient sky in the brand greens
    w = bpy.context.scene.world
    w.use_nodes = True
    wt = w.node_tree
    bg = wt.nodes["Background"]
    tc = wt.nodes.new("ShaderNodeTexCoord")
    sep = wt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = wt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
    ramp.color_ramp.elements[1].color = lin(GREENS[0])
    wt.links.new(tc.outputs["Generated"], sep.inputs[0])
    wt.links.new(sep.outputs["Y"], ramp.inputs["Fac"])
    wt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.2


def long_shadow():
    """A matte white dome right behind the grid and one hard, low green spot light: every glass
    piece throws a long, crisp shadow across the wall."""
    m, nt, out = new_material("dome-paper")
    d = nt.nodes.new("ShaderNodeBsdfDiffuse")
    d.inputs["Color"].default_value = lin("#eef2ea")
    nt.links.new(d.outputs[0], out.inputs["Surface"])
    set_dome(m)
    set_glass(glass(ior=1.55, tint=(0.9, 1.0, 0.85, 1)))      # faint green tint in the glass
    bpy.data.objects["Light"].hide_render = True
    ld = bpy.data.lights.new("sun-spot", "SPOT")
    ld.energy, ld.spot_size, ld.shadow_soft_size = 4000, 1.2, 0.0
    ld.color = lin(GREENS[0])[:3]
    sp = bpy.data.objects.new("sun-spot", ld)
    bpy.context.scene.collection.objects.link(sp)
    sp.location = (2.2, 1.6, -3.0)
    t = bpy.data.objects.new("spot-target", None)
    bpy.context.scene.collection.objects.link(t)
    t.location = (0.2, 0.0, 0.3)
    sp.constraints.new("TRACK_TO").target = t
    world("#0b0c0a", 0.05)


VARIANTS = {"greenhouse": greenhouse, "icon-dome": icon_dome, "mirror": mirror, "long-shadow": long_shadow}


def world(hex_color, strength):
    w = bpy.context.scene.world
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = lin(hex_color)
    bg.inputs["Strength"].default_value = strength


def render_settings(samples, scale):
    sc = bpy.context.scene
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
        bpy.ops.wm.open_mainfile(filepath=blend)          # start every variant from the untouched file
        VARIANTS[name]()
        render_settings(args.samples, args.scale)
        path = args.out or str(OUT / f"oma-dome--{name}.png")
        bpy.context.scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        print(f"[oma-dome] wrote {path}", flush=True)


main()
