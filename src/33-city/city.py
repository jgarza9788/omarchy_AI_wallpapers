"""33 — Package City: every installed thing as a building, at night (Blender/Cycles).

The real inventory (src/inventory.py, read from the cache .wip/inventory.json)
becomes a city:
  * each source is a district; districts are laid out as a squarified treemap
    with area ∝ the number of items, separated by streets on a faint glowing grid
  * each item is a building on its own lot. Height ∝ √size, so 4 KB scripts
    are sheds and 1 GB runtimes are towers; inside a district the biggest
    buildings stand in the middle, so every district grows its own downtown
  * windows glow in the district's theme colour; explicitly installed things
    have most windows lit, dependencies only a few
  * district names lie on the street in front of each district
Seen from a high isometric angle with an orthographic camera.

Usage:
  python3 src/inventory.py           # (once) cache the inventory outside Blender
  blender -b -P src/33-city/city.py -- --scheme omarchy [--samples 64] [--scale 100]
  blender -b -P src/33-city/city.py -- --scheme all
"""
import argparse
import json
import math
import pathlib
import random
import subprocess
import sys

import bmesh
import bpy
from mathutils import Vector

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "palettes"))
sys.path.insert(0, str(ROOT / "src"))
import palettes  # noqa: E402
import inventory  # noqa: E402

SCHEMES = ["omarchy", "tokyo-night", "retro-82", "osaka-jade"]
OUT = ROOT / "output" / "33-city"
STREET = 2.0                  # gap between districts
ASPECT = 16 / 9


def lin(hex_color, k=1.0):
    def f(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = palettes.rgb(hex_color)
    return (f(r) * k, f(g) * k, f(b) * k, 1.0)


def squarify(sizes, x, y, w, h):
    """Squarified treemap (Bruls et al.): sizes sorted desc, summing to w*h. Returns rects."""
    rects, items = [], list(sizes)
    while items:
        short = min(w, h)
        row, rest = [items[0]], items[1:]

        def worst(r):
            s = sum(r)
            return max(max(s * s / (short * short * v), short * short * v / (s * s)) for v in r)
        while rest and worst(row + [rest[0]]) <= worst(row):
            row.append(rest.pop(0))
        s = sum(row)
        if w >= h:                                   # lay the row along the left edge
            cw = s / h
            yy = y
            for v in row:
                rects.append((x, yy, cw, v / cw))
                yy += v / cw
            x, w = x + cw, w - cw
        else:
            rh = s / w
            xx = x
            for v in row:
                rects.append((xx, y, v / rh, rh))
                xx += v / rh
            y, h = y + rh, h - rh
        items = rest
    return rects


def window_material(name, color, lit):
    """Dark facade with a grid of windows (brick texture on world xz/yz); a fraction `lit` glow."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.05, 0.055, 0.07, 1)
    p.inputs["Roughness"].default_value = 0.6
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sep.inputs["Vector"])
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    nt.links.new(sep.outputs["X"], add.inputs[0])
    nt.links.new(sep.outputs["Y"], add.inputs[1])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(add.outputs["Value"], comb.inputs["X"])
    nt.links.new(sep.outputs["Z"], comb.inputs["Y"])
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.offset = 0.0
    br.inputs["Scale"].default_value = 1.0                 # world units: windows 0.12 wide, floors 0.2 tall
    br.inputs["Mortar Size"].default_value = 0.045
    br.inputs["Brick Width"].default_value = 0.17
    br.inputs["Row Height"].default_value = 0.2
    br.inputs["Bias"].default_value = 0.0
    br.inputs["Color1"].default_value = (1, 1, 1, 1)
    br.inputs["Color2"].default_value = (0, 0, 0, 1)
    nt.links.new(comb.outputs["Vector"], br.inputs["Vector"])
    # brick colour varies per brick between Color1/Color2: threshold it to pick the lit windows
    th = nt.nodes.new("ShaderNodeMath")
    th.operation = "GREATER_THAN"
    th.inputs[1].default_value = 1 - lit
    bw = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(br.outputs["Color"], bw.inputs["Color"])
    nt.links.new(bw.outputs["Val"], th.inputs[0])
    win = nt.nodes.new("ShaderNodeMath")                 # window (not mortar) and lit
    win.operation = "MULTIPLY"
    nt.links.new(th.outputs["Value"], win.inputs[0])
    inv = nt.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    nt.links.new(br.outputs["Fac"], inv.inputs[1])
    nt.links.new(inv.outputs["Value"], win.inputs[1])
    side = nt.nodes.new("ShaderNodeMath")                # facades only, not roofs
    side.operation = "LESS_THAN"
    sepn = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sepn.inputs["Vector"])
    nt.links.new(sepn.outputs["Z"], side.inputs[0])
    side.inputs[1].default_value = 0.5
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    nt.links.new(win.outputs["Value"], mul.inputs[0])
    nt.links.new(side.outputs["Value"], mul.inputs[1])
    strength = nt.nodes.new("ShaderNodeMath")
    strength.operation = "MULTIPLY"
    strength.inputs[1].default_value = 2.2
    nt.links.new(mul.outputs["Value"], strength.inputs[0])
    p.inputs["Emission Color"].default_value = color
    nt.links.new(strength.outputs["Value"], p.inputs["Emission Strength"])
    return m


def box(bm, x, y, w, d, h):
    verts = [bm.verts.new((x + dx, y + dy, z)) for z in (0, h) for dx, dy in ((0, 0), (w, 0), (w, d), (0, d))]
    for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        bm.faces.new([verts[i] for i in f])


def build(pal, inv):
    rnd = random.Random(7)
    colors = inventory.source_colors(pal)
    groups = [(s, [i for i in inv if i["source"] == s]) for s in inventory.SOURCES]
    groups = [g for g in groups if g[1]]
    groups.sort(key=lambda g: -len(g[1]))
    area = sum(len(g[1]) * 1.55 + 6 for g in groups)              # lots + a little air per district
    H = math.sqrt(area / ASPECT)
    Wd = H * ASPECT
    rects = squarify([len(g[1]) * 1.55 + 6 for g in groups], 0, 0, Wd, H)
    font_path = subprocess.run(["fc-match", "-f", "%{file}", "monospace"], capture_output=True, text=True).stdout.strip()
    font = bpy.data.fonts.load(font_path) if font_path else None

    for (src, items), (rx, ry, rw, rh) in zip(groups, rects):
        gap = min(STREET, 0.35 * min(rw, rh))                       # tiny districts get narrower streets
        x0, y0, w, h = rx + gap / 2, ry + gap / 2, rw - gap, rh - gap
        n = len(items)
        cols = max(1, round(math.sqrt(n * w / h)))
        rows = math.ceil(n / cols)
        lw, lh = w / cols, h / rows
        lots = [(c, r) for r in range(rows) for c in range(cols)]
        cx, cy = (cols - 1) / 2, (rows - 1) / 2
        lots.sort(key=lambda cr: (cr[0] - cx) ** 2 * (lh / lw) + (cr[1] - cy) ** 2 * (lw / lh) + rnd.random() * 0.8)
        items = sorted(items, key=lambda i: -i["bytes"])
        mats = {lit: window_material(f"win_{src}_{lit}", lin(colors[src]), lit) for lit in (0.18, 0.6)}
        me = {lit: bmesh.new() for lit in mats}
        for it, (c, r) in zip(items, lots):
            hgt = 0.25 + 9.0 * math.sqrt(it["bytes"] / 1e9)          # 1 GB ≈ 9 units, 1 MB ≈ 0.5
            fp = min(lw, lh) * (0.5 + 0.22 * min(hgt / 6, 1))
            bx = x0 + (c + 0.5) * lw - fp / 2 + rnd.uniform(-0.05, 0.05)
            by = y0 + (r + 0.5) * lh - fp / 2 + rnd.uniform(-0.05, 0.05)
            box(me[0.6 if it["explicit"] else 0.18], bx, by, fp, fp, hgt)
        for lit, bm in me.items():
            mesh = bpy.data.meshes.new(f"{src}_{lit}")
            bm.to_mesh(mesh)
            bm.free()
            ob = bpy.data.objects.new(f"{src}_{lit}", mesh)
            bpy.context.collection.objects.link(ob)
            ob.data.materials.append(mats[lit])
        # district label on the street, facing up
        bpy.ops.object.text_add(location=(x0 + 0.1, y0 - gap * 0.45, 0.01))
        tx = bpy.context.object
        tx.data.body = f"{inventory.LABELS[src].upper()}  {n}  {inventory.human(sum(i['bytes'] for i in items))}"
        if font:
            tx.data.font = font
        tx.data.size = 0.85
        lm = bpy.data.materials.new(f"label_{src}")
        lm.use_nodes = True
        lp = lm.node_tree.nodes["Principled BSDF"]
        lp.inputs["Emission Color"].default_value = lin(colors[src])
        lp.inputs["Emission Strength"].default_value = 1.5
        tx.data.materials.append(lm)

    # ground: dark asphalt with a faint street grid
    gm = bpy.data.materials.new("ground")
    gm.use_nodes = True
    nt = gm.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = lin(pal.get("darker_background", pal["background"]), 0.5)
    p.inputs["Roughness"].default_value = 0.5
    tc = nt.nodes.new("ShaderNodeTexCoord")
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.offset = 0.0
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Brick Width"].default_value = 2.0
    br.inputs["Row Height"].default_value = 2.0
    br.inputs["Mortar Size"].default_value = 0.02
    nt.links.new(tc.outputs["Object"], br.inputs["Vector"])
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = 0.25
    nt.links.new(br.outputs["Fac"], mul.inputs[0])
    p.inputs["Emission Color"].default_value = lin(pal["accent"])
    nt.links.new(mul.outputs["Value"], p.inputs["Emission Strength"])
    bpy.ops.mesh.primitive_plane_add(size=400, location=(Wd / 2, H / 2, 0))
    bpy.context.object.data.materials.append(gm)
    return Wd, H


def setup(pal, Wd, H, samples, scale):
    sc = bpy.context.scene
    target = Vector((Wd / 2, H / 2, 0.8))
    cam_d = bpy.data.cameras.new("cam")
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = Wd * 1.08
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    elev, azim = math.radians(38), math.radians(-62)
    cam.location = target + 80 * Vector((math.cos(elev) * math.cos(azim), math.cos(elev) * math.sin(azim), math.sin(elev)))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    moon = bpy.data.lights.new("moon", "SUN")
    moon.energy, moon.angle, moon.color = 1.6, math.radians(3), lin(pal.get("blue", pal["accent"]))[:3]
    mo = bpy.data.objects.new("moon", moon)
    sc.collection.objects.link(mo)
    mo.rotation_euler = (math.radians(50), 0, math.radians(140))
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = lin(pal["background"])
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    sc.world = world
    r = sc.render
    r.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    r.resolution_x, r.resolution_y, r.resolution_percentage = 3840, 2160, scale
    sc.view_settings.view_transform = "AgX"


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheme", default="omarchy")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--scale", type=int, default=100)
    args = ap.parse_args(argv)
    inv = json.loads(inventory.CACHE.read_text())
    for name in (SCHEMES if args.scheme == "all" else [args.scheme]):
        pal = palettes.load()[name]
        bpy.ops.wm.read_factory_settings(use_empty=True)
        Wd, H = build(pal, inv)
        setup(pal, Wd, H, args.samples, args.scale)
        out = OUT / f"city--{name}.png" if args.scale == 100 else ROOT / ".wip" / f"city--{name}@{args.scale}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        bpy.context.scene.render.filepath = str(out)
        bpy.ops.render.render(write_still=True)
        print("wrote", out)


main()
