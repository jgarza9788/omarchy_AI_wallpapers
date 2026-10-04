"""08 — Shroud: a silk sheet dropped over hidden forms (Blender cloth simulation).

Three forms hide under the cloth: a cylinder, a block and a 45°-turned block, the
circle, square and diamond of the OMA mark. You only see them through the way the
silk folds over them. Every colour scheme also gets its own drop (sheet rotation,
offset, a gust of wind), though these are small, so the drapes look alike. Rendered in
Cycles with one low, raking key light so the folds carry the image.

Usage:
  blender -b -P src/08-shroud/shroud.py -- --scheme kanagawa [--samples 64] [--scale 100] [--frames 90]
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

SILK = {"rose-pine": "red", "kanagawa": "blue", "everforest": "green", "retro-82": "accent", "vantablack": "background"}
SCHEMES = list(SILK)
OUT = ROOT / "output" / "08-shroud"


def lin(hex_color):
    def f(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = palettes.rgb(hex_color)
    return (f(r), f(g), f(b), 1.0)


def mat(name, color, rough, sheen=0.0, sheen_tint=None, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = color
    p.inputs["Roughness"].default_value = rough
    if "Sheen Weight" in p.inputs:
        p.inputs["Sheen Weight"].default_value = sheen
        if sheen_tint:
            p.inputs["Sheen Tint"].default_value = sheen_tint
    if "Coat Weight" in p.inputs:
        p.inputs["Coat Weight"].default_value = coat
    if sheen and "Anisotropic" in p.inputs:
        p.inputs["Anisotropic"].default_value = 0.7
    return m


def collider(ob, thickness=0.02):
    mod = ob.modifiers.new("collision", "COLLISION")
    ob.collision.thickness_outer = thickness
    ob.collision.cloth_friction = 8.0
    return ob


def build(name, pal, samples, scale, frames):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    rnd = random.Random(int(hashlib.sha256(name.encode()).hexdigest()[:8], 16))
    light_theme = pal["mode"] == "light"

    floor_col = lin(pal["background"])
    cloth_col = lin(pal[SILK.get(name, "accent")])
    if name == "vantablack":  # black silk on a dim grey floor
        floor_col = lin(pal.get("lighter_background", "#1a1a1a"))
    sheen_col = lin(pal.get("bright_foreground", pal["foreground"]))
    form_mat = mat("form", floor_col, 0.5)

    # hidden forms: circle, square, diamond (heights vary so the cloth tents)
    bpy.ops.mesh.primitive_cylinder_add(radius=1.05, depth=1.7, location=(-2.6, 0, 0.85), vertices=96)
    collider(bpy.context.object).data.materials.append(form_mat)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.0, 0, 0.6))
    sq = bpy.context.object
    sq.scale = (1.9, 1.9, 1.2)
    collider(sq).data.materials.append(form_mat)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(2.75, 0, 1.15), rotation=(0, 0, math.radians(45)))
    dm = bpy.context.object
    dm.scale = (1.45, 1.45, 2.3)
    collider(dm).data.materials.append(form_mat)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    # floor
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
    floor = collider(bpy.context.object, 0.01)
    floor.data.materials.append(mat("floor", floor_col, 0.65))

    # the silk sheet
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=200, y_subdivisions=150, size=1,
                                    location=(rnd.uniform(-0.4, 0.4), rnd.uniform(-0.3, 0.3), 3.0),
                                    rotation=(0, 0, math.radians(rnd.uniform(-14, 14))))
    sheet = bpy.context.object
    sheet.scale = (11.0, 8.2, 1)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    cl = sheet.modifiers.new("cloth", "CLOTH")
    s = cl.settings
    s.quality = 6
    s.mass = 0.15
    s.air_damping = 1.2
    s.tension_stiffness = s.compression_stiffness = 6
    s.shear_stiffness = 4
    s.bending_stiffness = 0.015
    s.bending_damping = 0.4
    cl.collision_settings.distance_min = 0.006
    cl.collision_settings.use_self_collision = False
    cl.point_cache.frame_end = frames
    sub = sheet.modifiers.new("smooth", "SUBSURF")
    sub.levels = 1
    sub.render_levels = 2
    sol = sheet.modifiers.new("thickness", "SOLIDIFY")
    sol.thickness = 0.008
    sheet.data.materials.append(mat("silk", cloth_col, 0.22, sheen=1.0, sheen_tint=sheen_col, coat=0.1))
    for p in sheet.data.polygons:
        p.use_smooth = True

    # a gust of wind gives each drape its own folds
    bpy.ops.object.effector_add(type="WIND", location=(rnd.uniform(-6, 6), rnd.uniform(-5, -3), 3),
                                rotation=(math.radians(rnd.uniform(60, 100)), 0, math.radians(rnd.uniform(-40, 40))))
    bpy.context.object.field.strength = rnd.uniform(40, 120)
    bpy.context.object.field.noise = rnd.uniform(0.5, 2.0)

    # simulate
    sc.frame_start, sc.frame_end = 1, frames
    for f in range(1, frames + 1):
        sc.frame_set(f)

    # lights: low raking key, soft fill from the other side, faint top
    def area(nm, loc, rot, color, energy, size):
        ld = bpy.data.lights.new(nm, "AREA")
        ld.color, ld.energy, ld.size = color[:3], energy, size
        ob = bpy.data.objects.new(nm, ld)
        ob.location, ob.rotation_euler = loc, rot
        sc.collection.objects.link(ob)

    warm = lin(pal.get("yellow", pal["foreground"]))
    cool = lin(pal.get("blue", pal["accent"]))
    key_az = math.radians(rnd.choice([-1, 1]) * rnd.uniform(55, 80))
    kx, ky = 11 * math.sin(key_az), -11 * math.cos(key_az)
    area("key", (kx, ky, 2.4), (math.radians(80), 0, key_az), tuple(0.75 + 0.25 * c for c in warm), 5200, 2.0)
    area("fill", (-kx * 0.8, -ky * 0.8, 6), (math.radians(50), 0, key_az + math.pi), cool, 90, 10)
    area("top", (0, 0, 10), (0, 0, 0), (1, 1, 1), 40, 14)

    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = floor_col
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.15
    sc.world = world

    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 42
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    cam.location = (2.2, -14.0, 5.0)
    target = bpy.data.objects.new("t", None)
    target.location = (0.2, 0.3, 1.5)
    sc.collection.objects.link(target)
    cam.constraints.new("TRACK_TO").target = target
    sc.camera = cam

    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 3840, 2160
    sc.render.resolution_percentage = scale
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Base Contrast"
    except TypeError:
        pass


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheme", default="all")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--scale", type=int, default=100)
    ap.add_argument("--frames", type=int, default=110)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    pals = palettes.load()
    OUT.mkdir(parents=True, exist_ok=True)
    for nm in (SCHEMES if args.scheme == "all" else [args.scheme]):
        build(nm, pals[nm], args.samples, args.scale, args.frames)
        path = args.out or str(OUT / f"shroud--{nm}.png")
        bpy.context.scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        print(f"[shroud] wrote {path}", flush=True)


main()
