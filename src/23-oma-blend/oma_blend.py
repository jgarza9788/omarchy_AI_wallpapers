"""23 — OMA Blend: wallpapers built from the hand-modelled OMA in assets/OMA.blend.

The .blend holds the three pieces stacked as one column, top to bottom:
O (Cylinder), M (Cube.002, notched by a Boolean with Cube.003) and A
(Cube.001). This script appends them, removes their Array modifiers, applies
the Boolean and bakes the column into a reusable unit. The O-M-A order and the
modelled orientation are kept exactly. It then builds one of these layouts:

  hero   one large crystal OMA on a black mirror floor, in front of a wall of
         glowing Nerd Font app icons that are the only real light in the scene
  grid   a grid of OMA columns rotating 0°→180° from left to right, with each row
         a different optical material, in front of the icon wall
  wave   a long field of OMA columns receding into the distance, the rotation
         travelling through them as a wave, with icons glowing in the floor

Every icon is a real Blender text object set in Iosevka Nerd Font with an emissive
material coloured from the theme, so the glass refracts and the metal reflects
actual icons.

Usage:
  blender -b -P src/23-oma-blend/oma_blend.py -- --layout grid --scheme tokyo-night [--samples 64] [--scale 100]
  blender -b -P src/23-oma-blend/oma_blend.py -- --layout all --scheme all
"""
import argparse
import hashlib
import math
import pathlib
import random
import sys

import bpy
from mathutils import Matrix, Vector

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "palettes"))
import palettes  # noqa: E402

BLEND = ROOT / "assets" / "OMA.blend"
FONT = ROOT / "assets" / "fonts" / "Iosevka" / "IosevkaNerdFontMono-Regular.ttf"
OUT = ROOT / "output" / "23-oma-blend"
PIECES = ["Cylinder", "Cube.002", "Cube.001"]          # O, M, A (top -> bottom in the .blend)
CUTTER = "Cube.003"
SCHEMES = {          # "omarchy" = official brand colours (see palettes/palettes.py)
    "hero": ["omarchy", "catppuccin", "matte-black"],
    "grid": ["omarchy", "gruvbox", "rose-pine"],
    "wave": ["omarchy", "osaka-jade", "retro-82"],
}
ICONS = [0xF303, 0xF17C, 0xF359, 0xF489, 0xF120, 0xF269, 0xF268, 0xE7C5, 0xF338, 0xE795, 0xF308, 0xE73C,
         0xE739, 0xE791, 0xF1BC, 0xF167, 0xE60B, 0xF0E0, 0xF1C0, 0xE706, 0xE7B1, 0xF07B, 0xF015, 0xF001,
         0xF03D, 0xF030, 0xF11B, 0xF1FC, 0xF0AD, 0xF121, 0xF126, 0xF09B, 0xF113, 0xF2DC, 0xF0C2, 0xF1EB,
         0xE702, 0xF418, 0xE62B, 0xE7A8, 0xE627, 0xE74E, 0xE620, 0xE718, 0xF013, 0xF233, 0xE615, 0xE737]

# .blend space -> world: the file is viewed from -Z with +Y up and screen-right = -X.
# World here is Z-up with the camera on -Y looking +Y, so X = -x, Y = z, Z = y.
FILE_TO_WORLD = Matrix(((-1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))


def lin(hex_color, a=1.0):
    def f(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = palettes.rgb(hex_color)
    return (f(r), f(g), f(b), a)


# --- the OMA unit ------------------------------------------------------------------
def load_unit():
    """Append the pieces and return {'O': mesh, 'M': mesh, 'A': mesh}, centred, in world axes."""
    with bpy.data.libraries.load(str(BLEND), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n in PIECES + [CUTTER]]
    objs = {o.name: o for o in dst.objects}
    for o in objs.values():
        bpy.context.scene.collection.objects.link(o)
    for n in PIECES:
        o = objs[n]
        for m in list(o.modifiers):
            if m.type == "NODES":               # the Array modifiers: we lay out copies ourselves
                o.modifiers.remove(m)
    dg = bpy.context.evaluated_depsgraph_get()
    meshes = {}
    for key, n in zip("OMA", PIECES):
        o = objs[n]
        me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
        me.transform(FILE_TO_WORLD @ o.matrix_world)
        meshes[key] = me
    for o in objs.values():
        bpy.data.objects.remove(o)
    # centre the column on its bounding box
    pts = [v.co for me in meshes.values() for v in me.vertices]
    c = Vector([(min(p[i] for p in pts) + max(p[i] for p in pts)) / 2 for i in range(3)])
    for me in meshes.values():
        me.transform(Matrix.Translation(-c))
        for p in me.polygons:
            p.use_smooth = False
    height = max(p[2] for p in pts) - min(p[2] for p in pts)
    return meshes, height


def place_unit(meshes, mats, matrix, name):
    """One OMA column = 3 objects sharing the baked meshes, under an empty."""
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    root.matrix_world = matrix
    for key in "OMA":
        ob = bpy.data.objects.new(f"{name}.{key}", meshes[key])
        bpy.context.scene.collection.objects.link(ob)
        ob.parent = root
        bev = ob.modifiers.new("bevel", "BEVEL")
        bev.width, bev.segments, bev.limit_method = 0.006, 3, "ANGLE"
        # meshes are shared between columns, so the material lives on the object, not the mesh
        if not ob.data.materials:
            ob.data.materials.append(None)
        ob.material_slots[0].link = "OBJECT"
        ob.material_slots[0].material = mats[key]
    return root


# --- materials ------------------------------------------------------------------------
def principled(name, **inputs):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    for k, v in inputs.items():
        key = k.replace("_", " ")
        if key in p.inputs:
            p.inputs[key].default_value = v
    return m


def material_set(pal):
    acc = lin(pal["accent"])
    tint = tuple(0.4 + 0.6 * c for c in acc[:3]) + (1,)
    return {
        "crystal": principled("crystal", Base_Color=(0.93, 0.96, 1.0, 1), Transmission_Weight=1.0, Roughness=0.0, IOR=1.75),
        "tinted": principled("tinted", Base_Color=tint, Transmission_Weight=1.0, Roughness=0.02, IOR=1.5),
        "chrome": principled("chrome", Base_Color=(0.95, 0.95, 0.97, 1), Metallic=1.0, Roughness=0.04),
        "iridescent": principled("iridescent", Base_Color=(0.92, 0.92, 0.96, 1), Transmission_Weight=1.0,
                                 Roughness=0.0, IOR=1.5, Thin_Film_Thickness=560.0, Thin_Film_IOR=1.33),
        "frosted": principled("frosted", Base_Color=(1, 1, 1, 1), Transmission_Weight=1.0, Roughness=0.3, IOR=1.45),
        "gold": principled("gold", Base_Color=lin(pal.get("yellow", "#e0af68")), Metallic=1.0, Roughness=0.18),
        "black": principled("black", Base_Color=(0.01, 0.01, 0.012, 1), Roughness=0.08, Coat_Weight=1.0),
    }


def same(m):
    return {"O": m, "M": m, "A": m}


# --- icons & environment ------------------------------------------------------------------
def icon_wall(pal, rng, cols, rows, pitch, origin, normal="wall", strength=4.0, scale=0.78, fill=1.0):
    """A grid of emissive Nerd Font icons. normal='wall' -> in the XZ plane facing -Y; 'floor' -> XY plane."""
    font = bpy.data.fonts.load(str(FONT), check_existing=True)
    palette = [pal[k] for k in ("accent", "blue", "cyan", "magenta", "green", "yellow", "red") if k in pal]
    if "oma_bands" in pal:      # official palette: icons glow in the logo's own greens
        palette = pal["oma_bands"][:4] + [pal["foreground"]]
    mats = {}
    for hx in palette:
        m = bpy.data.materials.new(f"glow{hx}")
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.remove(nt.nodes["Principled BSDF"])
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = lin(hx)
        e.inputs["Strength"].default_value = strength
        nt.links.new(e.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
        mats[hx] = m
    for i in range(cols):
        for j in range(rows):
            if rng.random() > fill:
                continue
            cu = bpy.data.curves.new(f"ic{i}_{j}", "FONT")
            cu.font = font
            cu.body = chr(ICONS[rng.randrange(len(ICONS))])
            cu.align_x, cu.align_y = "CENTER", "CENTER"
            cu.size = pitch * scale
            ob = bpy.data.objects.new(cu.name, cu)
            bpy.context.scene.collection.objects.link(ob)
            u, v = (i - (cols - 1) / 2) * pitch, (j - (rows - 1) / 2) * pitch
            if normal == "wall":
                ob.location = (origin[0] + u, origin[1], origin[2] + v)
                ob.rotation_euler = (math.pi / 2, 0, 0)
            else:
                ob.location = (origin[0] + u, origin[1] + v, origin[2])
            cu.materials.append(mats[palette[rng.randrange(len(palette))]])


def backdrop(pal, y, glossy=0.35, glow=0.05):
    """Dark wall with a soft radial glow in the theme accent, so glass has colour to bend."""
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, y + 0.01, 0), rotation=(math.pi / 2, 0, 0))
    m = principled("wall", Base_Color=lin(pal.get("darker_background", pal["background"])), Roughness=glossy,
                   Emission_Color=lin(pal["accent"]))
    nt = m.node_tree
    tex = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / 9.0, 1 / 6.0, 1)
    mp.inputs["Location"].default_value = (0, -0.1, 0)
    gr = nt.nodes.new("ShaderNodeTexGradient")
    gr.gradient_type = "SPHERICAL"
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = glow
    nt.links.new(tex.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], gr.inputs["Vector"])
    nt.links.new(gr.outputs["Fac"], mul.inputs[0])
    nt.links.new(mul.outputs[0], nt.nodes["Principled BSDF"].inputs["Emission Strength"])
    bpy.context.object.data.materials.append(m)


def studio(pal, rng, centre=(0, 0, 1.2), mirror_icons=True):
    """Hidden softboxes for specular edges + an icon wall behind the camera for metals to reflect."""
    cx, cy, cz = centre

    def softbox(name, loc, rot, energy, size, color=(1, 1, 1)):
        area(name, loc, rot, color, energy, size)
        ob = bpy.data.objects[name]
        ob.visible_camera = False
        ob.visible_diffuse = False      # specular only: edges light up, the room stays dark

    softbox("top", (cx, cy - 1.5, cz + 5), (math.radians(15), 0, 0), 900, 6)
    softbox("left", (cx - 6, cy - 2, cz + 1), (math.radians(90), 0, math.radians(-70)), 500, 3, lin(pal["accent"])[:3])
    softbox("right", (cx + 6, cy - 2, cz + 1), (math.radians(90), 0, math.radians(70)), 500, 3,
            lin(pal.get("magenta", pal["accent"]))[:3])
    if mirror_icons:
        n0 = len(bpy.data.objects)
        icon_wall(pal, rng, 22, 10, 0.55, (cx, cy - 10.0, cz), strength=5.0)
        for o in list(bpy.data.objects)[n0:]:
            if o.type == "FONT":
                o.visible_camera = False
                o.rotation_euler = (math.pi / 2, 0, math.pi)


def mirror_floor(pal, z, rough=0.06):
    bpy.ops.mesh.primitive_plane_add(size=120, location=(0, 0, z))
    bpy.context.object.data.materials.append(
        principled("floor", Base_Color=lin(pal.get("darker_background", pal["background"])), Roughness=rough,
                   Coat_Weight=0.6))


def world(pal, strength=0.08):
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = lin(pal["background"])
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = strength
    bpy.context.scene.world = w


def camera(loc, target, lens=50, ortho=None, dof=None):
    data = bpy.data.cameras.new("cam")
    data.lens = lens
    if ortho:
        data.type, data.ortho_scale = "ORTHO", ortho
    cam = bpy.data.objects.new("cam", data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = loc
    t = bpy.data.objects.new("target", None)
    bpy.context.scene.collection.objects.link(t)
    t.location = target
    cam.constraints.new("TRACK_TO").target = t
    if dof:
        data.dof.use_dof, data.dof.focus_object, data.dof.aperture_fstop = True, t, dof
    bpy.context.scene.camera = cam


def area(name, loc, rot, color, energy, size):
    ld = bpy.data.lights.new(name, "AREA")
    ld.color, ld.energy, ld.size = color[:3], energy, size
    ob = bpy.data.objects.new(name, ld)
    ob.location, ob.rotation_euler = loc, rot
    bpy.context.scene.collection.objects.link(ob)


# --- layouts ----------------------------------------------------------------------------
def layout_hero(pal, rng, meshes, h):
    mats = material_set(pal)
    k = 2.6 / h                                             # column ~2.6 m tall
    place_unit(meshes, same(mats["crystal"]),
               Matrix.Translation((0, 0, 1.3 + 0.02)) @ Matrix.Rotation(math.radians(rng.uniform(18, 32)), 4, "Z")
               @ Matrix.Scale(k, 4), "hero")
    icon_wall(pal, rng, 30, 14, 0.42, (0, 2.6, 2.6), strength=6.0)
    backdrop(pal, 2.62, glossy=0.85)
    mirror_floor(pal, 0.0)
    world(pal, 0.04)
    studio(pal, rng, centre=(0, 0, 1.3))
    camera((1.0, -9.6, 1.3), (0, 0, 1.3), lens=50, dof=5.6)


def layout_grid(pal, rng, meshes, h):
    mats = material_set(pal)
    rows = [mats["crystal"], mats["chrome"], mats["iridescent"]]
    cols = 9
    k = 0.95 / h                                            # each column ~0.95 m tall
    for r, mat in enumerate(rows):
        for c in range(cols):
            ang = math.radians(180 * c / (cols - 1))         # 0° -> 180°, left to right
            x = (c - (cols - 1) / 2) * 0.62
            z = 2.35 - r * 1.15
            place_unit(meshes, same(mat), Matrix.Translation((x, 0, z)) @ Matrix.Rotation(ang, 4, "Z")
                       @ Matrix.Scale(k, 4), f"g{r}_{c}")
    icon_wall(pal, rng, 26, 12, 0.36, (0, 1.6, 1.2), strength=5.0)
    backdrop(pal, 1.62)
    world(pal, 0.05)
    studio(pal, rng, centre=(0, 0, 1.2))
    camera((0, -12, 1.2), (0, 0, 1.2), ortho=6.35)


def layout_wave(pal, rng, meshes, h):
    mats = material_set(pal)
    k = 1.15 / h
    nx, ny = 9, 4
    for i in range(nx):
        for j in range(ny):
            x = (i - (nx - 1) / 2) * 0.85
            y = j * 1.2
            phase = (i / (nx - 1)) * 2 * math.pi - j * 0.55       # rotation travels left -> right and back
            ang = math.pi / 2 * (1 - math.cos(phase))             # 0..180°
            mat = mats["black"] if j % 2 else mats["crystal"]
            place_unit(meshes, same(mat), Matrix.Translation((x, y, 0.575 + 0.004)) @ Matrix.Rotation(ang, 4, "Z")
                       @ Matrix.Scale(k, 4), f"w{i}_{j}")
    icon_wall(pal, rng, 40, 24, 0.27, (0, 2.6, 0.001), normal="floor", strength=4.0, scale=0.6, fill=0.55)
    mirror_floor(pal, 0.0, rough=0.12)
    world(pal, 0.03)
    backdrop(pal, 9.0, glossy=0.9, glow=0.08)
    studio(pal, rng, centre=(0, 2.0, 0.5))
    camera((0.0, -4.6, 3.6), (0, 2.0, 0.3), lens=34, dof=8.0)


LAYOUTS = {"hero": layout_hero, "grid": layout_grid, "wave": layout_wave}


def build(layout, name, pal, samples, scale):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    rng = random.Random(int(hashlib.sha256(f"{layout}{name}".encode()).hexdigest()[:8], 16))
    meshes, h = load_unit()
    LAYOUTS[layout](pal, rng, meshes, h)
    sc = bpy.context.scene
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


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", default="all")
    ap.add_argument("--scheme", default="all")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--scale", type=int, default=100)
    ap.add_argument("--out", default=None)
    ap.add_argument("--clay", action="store_true", help="debug: replace all OMA materials with white clay")
    args = ap.parse_args(argv)
    pals = palettes.load()
    OUT.mkdir(parents=True, exist_ok=True)
    for layout in (LAYOUTS if args.layout == "all" else [args.layout]):
        for nm in (SCHEMES[layout] if args.scheme == "all" else [args.scheme]):
            build(layout, nm, pals[nm], args.samples, args.scale)
            if args.clay:
                clay = principled("clay", Base_Color=(0.8, 0.8, 0.8, 1), Roughness=0.6)
                for o in bpy.context.scene.objects:
                    if o.type == "MESH" and o.parent is not None:
                        o.material_slots[0].material = clay
                area("clay_key", (-3, -6, 6), (math.radians(50), 0, math.radians(-30)), (1, 1, 1), 2500, 6)
            path = args.out or str(OUT / f"oma-{layout}--{nm}.png")
            bpy.context.scene.render.filepath = path
            bpy.ops.render.render(write_still=True)
            print(f"[oma-blend] wrote {path}", flush=True)


main()
