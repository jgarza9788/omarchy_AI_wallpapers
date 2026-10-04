"""31 — Loupe: the OMA logo cut from thick optical glass, lying on a lightbox (Blender/Cycles).

The O, M and A outlines (exact, from src/oma_shapes.py) are extruded into thick
slabs of glass with polished, bevelled edges and dropped onto a backlit light
table printed with glowing app icons (the Icon Dome texture). The camera looks
down at them like a loupe on a slide viewer: through each slab the icons are
shifted and magnified, the bevels catch bright refracted edge lines, and a low
raking spot throws faint refracted caustics across the table.
Unlike 23's crystal OMA standing in front of an icon wall, here the glass is
seen top-down against its own light source, so it is never "glass on black".

Usage:
  blender -b -P src/31-loupe/loupe.py -- --scheme omarchy [--samples 128] [--scale 100]
  blender -b -P src/31-loupe/loupe.py -- --scheme all
  blender -b -P src/31-loupe/loupe.py -- --scheme omarchy --glass all     # clear, tinted and frosted glass
Glass variants: clear; tinted green, blue, red, amber, violet, cyan (in the theme's own
hues); frosted (roughness 0.24) clear and in every tint,
plus light (0.1) and heavy (0.45) frost. Clear renders are loupe--<scheme>,
the others loupe-<variant>--<scheme>.
Glass types: smoke, opal (milky), reeded (fluted ribs), hammered (dimpled),
iridescent (thin film) and dichroic (tinted thin film).
"""
import argparse
import math
import pathlib
import sys

import bmesh
import bpy
from mathutils import Vector

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "palettes"))
sys.path.insert(0, str(ROOT / "src"))
import palettes  # noqa: E402
from oma_shapes import PIECES  # noqa: E402

SCHEMES = ["omarchy", "tokyo-night", "catppuccin", "everforest"]
OUT = ROOT / "output" / "31-loupe"
ICONS = ROOT / "src" / "24-oma-dome" / "icons.png"
K = 0.0105                         # logo svg units -> metres-ish (the logo is ~7.5 units wide)
THICK = 0.55
# (dx, dy, rotation°) per piece: a little scattered, as if dropped on the table
# variant -> (palette key for the tint or None, roughness); frosted glass scatters what it shows
GLASS = {"clear": (None, 0.0), "green": ("green", 0.0), "blue": ("blue", 0.0), "red": ("red", 0.0),
         "amber": ("yellow", 0.0), "violet": ("magenta", 0.0), "cyan": ("cyan", 0.0),
         "frost": (None, 0.24), "frost-green": ("green", 0.24), "frost-blue": ("blue", 0.24),
         "frost-red": ("red", 0.24), "frost-amber": ("yellow", 0.24), "frost-violet": ("magenta", 0.24),
         "frost-cyan": ("cyan", 0.24), "frost-light": (None, 0.1), "frost-heavy": (None, 0.45),
         "frost-light-green": ("green", 0.1), "frost-heavy-blue": ("blue", 0.45)}
# glass *types* beyond tint and frost: variant -> extra properties for glass_material
TYPES = {"smoke": {"tint": "smoke"},                                   # dark neutral grey glass
         "opal": {"rough": 0.5, "milk": 0.35},                         # milky, nearly opaque
         "reeded": {"bump": "wave"},                                   # fluted / ribbed bathroom glass
         "hammered": {"bump": "voronoi"},                              # beaten, dimpled surface
         "iridescent": {"film": 550},                                  # soap-bubble thin film
         "dichroic": {"film": 380, "tint": "magenta"}}                 # tinted + thin-film colour shift
GLASS.update({k: (v.get("tint"), v.get("rough", 0.0)) for k, v in TYPES.items()})
LAYOUT = {"O": (-0.35, 0.12, 5.0), "M": (0.0, 0.0, -4.0), "A": (0.45, -0.2, 9.0)}


def lin(hex_color, k=1.0):
    def f(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = palettes.rgb(hex_color)
    return (f(r) * k, f(g) * k, f(b) * k, 1.0)


def slab(name, poly, mat):
    """Extrude a 2D outline (svg units, y down) into a bevelled glass slab resting on z = 0."""
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vs = [bm.verts.new(((x - cx) * K, (cy - y) * K, 0.0)) for x, y in poly]
    face = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    bmesh.ops.translate(bm, vec=(0, 0, THICK), verts=[v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)
    bev = ob.modifiers.new("bevel", "BEVEL")
    bev.width, bev.segments, bev.limit_method = 0.16, 8, "ANGLE"
    bev.angle_limit = math.radians(30)
    ob.modifiers.new("wn", "WEIGHTED_NORMAL")
    for p in me.polygons:
        p.use_smooth = True
    return ob, ((cx - 400) * K, (400 - cy) * K)


def glass_material(pal, variant="clear"):
    """Optical glass. `variant` is clear, a tint (green, blue, ...) and/or frosted: see GLASS."""
    tint_key, rough = GLASS[variant]
    m = bpy.data.materials.new("glass")
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    extra = TYPES.get(variant, {})
    if tint_key == "smoke":
        p.inputs["Base Color"].default_value = (0.42, 0.42, 0.44, 1)
    elif tint_key:                                   # coloured glass, in the theme's own hue
        t = lin(next(pal[k] for k in (tint_key, "accent") if isinstance(pal.get(k), str)))
        p.inputs["Base Color"].default_value = tuple(0.6 + 0.4 * c for c in t[:3]) + (1,)   # light: it compounds per bounce
    else:                                            # clear: only a breath of the accent
        t = lin(pal["accent"])
        p.inputs["Base Color"].default_value = tuple(0.9 + 0.1 * c for c in t[:3]) + (1,)
    p.inputs["Transmission Weight"].default_value = 1.0
    p.inputs["Roughness"].default_value = rough
    p.inputs["IOR"].default_value = 1.52
    if "Dispersion" in p.inputs:                     # Cycles spectral dispersion (Abbe-style amount)
        p.inputs["Dispersion"].default_value = 0.6
    if "film" in extra and "Thin Film Thickness" in p.inputs:
        p.inputs["Thin Film Thickness"].default_value = extra["film"]       # nm
        p.inputs["Thin Film IOR"].default_value = 1.9
    if "milk" in extra:                              # opal: a little diffuse white mixed in
        p.inputs["Transmission Weight"].default_value = 1 - extra["milk"]
        p.inputs["Base Color"].default_value = (0.92, 0.93, 0.95, 1)
    if "bump" in extra:
        nt = m.node_tree
        tc = nt.nodes.new("ShaderNodeTexCoord")
        if extra["bump"] == "wave":                  # parallel rounded ribs across each piece
            tex = nt.nodes.new("ShaderNodeTexWave")
            tex.wave_type, tex.bands_direction, tex.wave_profile = "BANDS", "X", "SIN"
            tex.inputs["Scale"].default_value = 2.2
            tex.inputs["Distortion"].default_value = 0.0
            out, strength = tex.outputs["Fac"], 0.6
        else:                                        # dimples: smooth F1 distance
            tex = nt.nodes.new("ShaderNodeTexVoronoi")
            tex.feature = "SMOOTH_F1"
            tex.inputs["Scale"].default_value = 3.0
            out, strength = tex.outputs["Distance"], 0.45
        nt.links.new(tc.outputs["Object"], tex.inputs["Vector"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = strength
        bump.inputs["Distance"].default_value = 0.05
        nt.links.new(out, bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    return m


def lightbox_material(pal):
    """Diffuse table that also emits: dim theme glow with bright icons (from icons.png)."""
    m = bpy.data.materials.new("lightbox")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = lin(pal["background"], 0.7)
    p.inputs["Roughness"].default_value = 0.6
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(ICONS))
    tex.image.colorspace_settings.name = "Non-Color"
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 1.1, 1)           # ~0.55-unit icon cells on the 26 x 14.6 table
    nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = lin(pal["background"], 0.6)
    mix.inputs["B"].default_value = lin(pal.get("bright_foreground", pal["foreground"]))
    nt.links.new(tex.outputs["Color"], mix.inputs["Factor"])
    # every few icons glow in the accent instead
    nz = nt.nodes.new("ShaderNodeTexVoronoi")
    nz.inputs["Scale"].default_value = 9.0
    nz.feature = "F1"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = 0.72, 0.74
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Color"], ramp.inputs["Fac"])
    mix2 = nt.nodes.new("ShaderNodeMix")
    mix2.data_type = "RGBA"
    nt.links.new(mix.outputs["Result"], mix2.inputs["A"])
    acc = nt.nodes.new("ShaderNodeMix")
    acc.data_type = "RGBA"
    acc.inputs["A"].default_value = lin(pal["background"], 0.6)
    acc.inputs["B"].default_value = lin(pal["accent"])
    nt.links.new(tex.outputs["Color"], acc.inputs["Factor"])
    nt.links.new(acc.outputs["Result"], mix2.inputs["B"])
    nt.links.new(ramp.outputs["Color"], mix2.inputs["Factor"])
    nt.links.new(mix2.outputs["Result"], p.inputs["Emission Color"])
    p.inputs["Emission Strength"].default_value = 1.4
    return m


def build(pal, variant="clear"):
    glass = glass_material(pal, variant)
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
    table = bpy.context.object
    table.scale = (26, 26 * 9 / 16, 1)
    table.data.materials.append(lightbox_material(pal))
    for key, fn in PIECES.items():
        ob, (x, y) = slab(key, fn(), glass)
        dx, dy, rot = LAYOUT[key]
        ob.location = (x + dx, y + dy, 0.002)
        ob.rotation_euler = (0, 0, math.radians(rot))


def setup(pal, samples, scale):
    sc = bpy.context.scene
    target = Vector((0.0, 0.1, 0.2))
    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = 50
    cam_d.dof.use_dof = True
    cam_d.dof.aperture_fstop = 2.8
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    elev, azim = math.radians(55), math.radians(-100)
    dist = 16.0
    cam.location = target + Vector((dist * math.cos(elev) * math.cos(azim), dist * math.cos(elev) * math.sin(azim),
                                    dist * math.sin(elev)))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam_d.dof.focus_distance = (target - cam.location).length
    sc.camera = cam

    spot = bpy.data.lights.new("rake", "SPOT")
    spot.energy, spot.spot_size, spot.shadow_soft_size = 5000, math.radians(30), 0.05
    spot.color = (1, 0.97, 0.92)
    so = bpy.data.objects.new("rake", spot)
    sc.collection.objects.link(so)
    so.location = (-9, 5, 4.5)
    so.rotation_euler = (Vector((0.5, -0.4, 0)) - so.location).to_track_quat("-Z", "Y").to_euler()
    soft = bpy.data.lights.new("soft", "AREA")
    soft.size, soft.energy = 6, 400
    st = bpy.data.objects.new("soft", soft)
    sc.collection.objects.link(st)
    st.location = (3, -3, 7)
    st.rotation_euler = (Vector((0, 0, 0)) - st.location).to_track_quat("-Z", "Y").to_euler()
    st.visible_diffuse = False                         # specular-only: a highlight on every bevel

    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = lin(pal["background"])
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.3
    sc.world = world
    r = sc.render
    r.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.caustics_refractive = True
    sc.cycles.max_bounces = 16
    sc.cycles.transmission_bounces = 16
    r.resolution_x, r.resolution_y, r.resolution_percentage = 3840, 2160, scale
    sc.view_settings.view_transform = "AgX"


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheme", default="omarchy")
    ap.add_argument("--samples", type=int, default=128)
    ap.add_argument("--scale", type=int, default=100)
    ap.add_argument("--glass", default="clear", help="a variant from GLASS, or all")
    args = ap.parse_args(argv)
    variants = list(GLASS) if args.glass == "all" else [args.glass]
    for name in (SCHEMES if args.scheme == "all" else [args.scheme]):
        for variant in variants:
            pal = palettes.load()[name]
            bpy.ops.wm.read_factory_settings(use_empty=True)
            build(pal, variant)
            setup(pal, args.samples, args.scale)
            stem = "loupe" if variant == "clear" else f"loupe-{variant}"
            out = OUT / f"{stem}--{name}.png" if args.scale == 100 else ROOT / ".wip" / f"{stem}--{name}@{args.scale}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            bpy.context.scene.render.filepath = str(out)
            bpy.ops.render.render(write_still=True)
            print("wrote", out)


main()
