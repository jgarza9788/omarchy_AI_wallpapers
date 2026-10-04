"""29 — Keymap: your Hyprland bindings, built as a keyboard (Blender/Cycles).

Parses the real bindings: Omarchy's defaults (/usr/share/omarchy/default/hypr/
bindings/*.lua) and then the user's ~/.config/hypr/bindings.lua, applying its
hl.unbind() calls and its own o.bind()s. Loops over the workspace keys
(`"SUPER + " .. key` with key = code:10..19) expand to the digit row.

Each key of a 75% ANSI keyboard becomes a bevelled keycap:
  * height grows with the number of bindings on that key (modifiers count every
    chord they take part in), so the keyboard becomes a skyline of your habits
  * keycaps are frosted glass; bound ones are tinted and glow from inside in
    the accent colour (brighter = more bindings), with white-hot legends and an
    under-glow on the plate; unbound keys stay low, clear and unlit
  * legends use the system monospace font (FiraCode Nerd Font Mono on Omarchy)
  * the keys sit directly on an endless glowing 1u grid (no plate), which
    shows through the glass
Seen at a raking angle with shallow depth of field.

Usage:
  blender -b -P src/29-keymap/keymap.py -- --scheme omarchy [--samples 96] [--scale 100]
  blender -b -P src/29-keymap/keymap.py -- --scheme all
"""
import argparse
import collections
import math
import pathlib
import re
import subprocess
import sys

import bpy
from mathutils import Vector

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "palettes"))
import palettes  # noqa: E402

SCHEMES = ["omarchy", "tokyo-night", "hackerman", "rose-pine"]
OUT = ROOT / "output" / "29-keymap"
FONT_FALLBACK = ROOT / "assets" / "fonts" / "Iosevka" / "IosevkaNerdFontMono-Regular.ttf"
DEFAULTS = pathlib.Path("/usr/share/omarchy/default/hypr/bindings")
USER = pathlib.Path.home() / ".config" / "hypr" / "bindings.lua"
MODS = {"SUPER", "SHIFT", "CTRL", "ALT"}
CODES = {**{10 + i: str((i + 1) % 10) for i in range(10)}, 20: "MINUS", 21: "EQUAL", 34: "BRACKETLEFT",
         35: "BRACKETRIGHT", 47: "SEMICOLON", 48: "APOSTROPHE", 49: "GRAVE", 51: "BACKSLASH"}
ALIAS = {"ESC": "ESCAPE", "ENTER": "RETURN", "COMMA": "COMMA", "PERIOD": "PERIOD", "DOT": "PERIOD"}
BIND = re.compile(r'(?:o\.bind(?:_toggle)?|hl\.bind)\(\s*"([^"]+)"\s*(\.\.\s*\w+\s*)?,')
UNBIND = re.compile(r'hl\.unbind\(\s*"([^"]+)"\s*(\.\.\s*\w+\s*)?\)')


def combos(text, rx):
    out = []
    for line in text.splitlines():
        line = line.split("--")[0]
        for m in rx.finditer(line):
            combo, loop = m.groups()
            if loop:                               # `"SUPER + " .. key` → every digit key
                out += [combo.rstrip() + f" code:{c}" for c in range(10, 20)]
            else:
                out.append(combo)
    return out


def key_of(token):
    t = token.strip()
    if t.lower().startswith("code:"):
        return CODES.get(int(t[5:]))
    t = t.upper()
    return ALIAS.get(t, t)


def parse(combo):
    parts = [p for p in re.split(r"\s*\+\s*|\s+", combo.strip()) if p]
    mods = frozenset(p.upper() for p in parts if p.upper() in MODS)
    keys = [key_of(p) for p in parts if p.upper() not in MODS]
    return mods, (keys[-1] if keys else None)


def bindings():
    active = {}
    for f in sorted(DEFAULTS.glob("*.lua")):
        for c in combos(f.read_text(), BIND):
            active[parse(c)] = c
    user = USER.read_text() if USER.exists() else ""
    for c in combos(user, UNBIND):
        active.pop(parse(c), None)
    for c in combos(user, BIND):
        active[parse(c)] = c
    per_key = collections.Counter()
    for mods, key in active:
        if key is None or key.startswith(("MOUSE", "XF86")):
            continue
        per_key[key] += 1
        for m in mods:
            per_key[m] += 1
    return per_key, len(active)


# 75% ANSI layout: (key, legend, width in u); None = gap
ROWS = [
    [("ESCAPE", "esc", 1), None] + [(f"F{i}", f"F{i}", 1) for i in range(1, 13)],
    [("GRAVE", "`", 1)] + [(str(d), str(d), 1) for d in "1234567890"] + [("MINUS", "-", 1), ("EQUAL", "=", 1), ("BACKSPACE", "bksp", 2)],
    [("TAB", "tab", 1.5)] + [(k, k, 1) for k in "QWERTYUIOP"] + [("BRACKETLEFT", "[", 1), ("BRACKETRIGHT", "]", 1), ("BACKSLASH", "\\", 1.5)],
    [("CAPS", "caps", 1.75)] + [(k, k, 1) for k in "ASDFGHJKL"] + [("SEMICOLON", ";", 1), ("APOSTROPHE", "'", 1), ("RETURN", "enter", 2.25)],
    [("SHIFT", "shift", 2.25)] + [(k, k, 1) for k in "ZXCVBNM"] + [("COMMA", ",", 1), ("PERIOD", ".", 1), ("SLASH", "/", 1), ("SHIFT", "shift", 1.75), None, ("UP", "↑", 1)],
    [("CTRL", "ctrl", 1.25), ("SUPER", "\uf303", 1.25), ("ALT", "alt", 1.25), ("SPACE", "", 6.25), ("ALT", "alt", 1.25), ("CTRL", "ctrl", 1.25),
     None, ("LEFT", "←", 1), ("DOWN", "↓", 1), ("RIGHT", "→", 1)],
]


def lin(hex_color, k=1.0):
    def f(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = palettes.rgb(hex_color)
    return (f(r) * k, f(g) * k, f(b) * k, 1.0)


def system_font():
    """The system monospace font (FiraCode Nerd Font Mono on Omarchy), SemiBold if installed."""
    try:
        path = pathlib.Path(subprocess.run(["fc-match", "-f", "%{file}", "monospace"],
                                           capture_output=True, text=True, check=True).stdout.strip())
        bold = path.with_name(path.name.replace("-Regular", "-SemiBold"))
        return bold if bold.exists() else path
    except (OSError, subprocess.CalledProcessError):
        return FONT_FALLBACK


def glass(name, color, rough=0.05, emit=None, strength=0.0):
    """Frosted keycap glass: transmissive, lightly tinted, optionally glowing from inside."""
    m = material(name, color, rough=rough, emit=emit, strength=strength)
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Transmission Weight"].default_value = 1.0
    p.inputs["IOR"].default_value = 1.45
    return m


def grid_floor(pal, size=400.0):
    """Huge dark floor with glowing 1u grid lines (brick texture, zero offset = a square grid)."""
    m = bpy.data.materials.new("grid")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = lin(pal.get("darker_background", pal["background"]), 0.6)
    p.inputs["Roughness"].default_value = 0.35
    tc = nt.nodes.new("ShaderNodeTexCoord")
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.offset, br.squash = 0.0, 1.0
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Brick Width"].default_value = 1.0
    br.inputs["Row Height"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.025
    br.inputs["Mortar Smooth"].default_value = 0.3
    nt.links.new(tc.outputs["Object"], br.inputs["Vector"])
    p.inputs["Emission Color"].default_value = lin(pal["accent"])
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = 0.9
    nt.links.new(br.outputs["Fac"], mul.inputs[0])          # Fac is 1 in the mortar (the grid lines)
    nt.links.new(mul.outputs["Value"], p.inputs["Emission Strength"])
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, -0.001))
    ob = bpy.context.object
    ob.data.materials.append(m)
    return ob


def material(name, color, rough=0.5, emit=None, strength=0.0, metallic=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = color
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metallic
    if emit is not None:
        p.inputs["Emission Color"].default_value = emit
        p.inputs["Emission Strength"].default_value = strength
    return m


def cube(name, loc, size, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    ob = bpy.context.object
    ob.name = name
    ob.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    ob.data.materials.append(mat)
    if bevel:
        b = ob.modifiers.new("bevel", "BEVEL")
        b.width, b.segments = bevel, 4
        bpy.ops.object.shade_smooth()
    return ob


def build(pal, per_key):
    accent = lin(pal["accent"])
    fg = lin(pal["foreground"])
    cap_dark = glass("cap_dark", lin(pal["foreground"], 0.8), rough=0.08)
    hot = lin(pal.get("bright_foreground", pal["foreground"]))
    legend_dim = material("legend_dim", fg, emit=fg, strength=0.03)
    font = bpy.data.fonts.load(str(system_font()))
    top = max([v for k, v in per_key.items() if k not in MODS] or [1])

    U, gap = 1.0, 0.08
    y = 0.0
    width = 0
    for r, row in enumerate(ROWS):
        x = 0.0
        if r == 1:
            y -= 0.25                                       # gap under the F-row
        for item in row:
            if item is None:
                x += 0.5 if r in (0,) else 0.25
                continue
            key, legend, wu = item
            n = per_key.get(key, 0)
            t = min(math.log1p(n) / math.log1p(top), 1.0)    # modifiers saturate at the top
            hgt = 0.25 + 1.9 * t ** 1.4
            cx, cy = x + wu * U / 2, y - U / 2
            cube(f"cap_{key}_{r}_{x}", (cx, cy, hgt / 2), (wu * U - gap, U - gap, hgt), (glass(f"capm_{key}_{r}_{x}", tuple(0.22 * a + 0.78 * b for a, b in zip(accent, (1, 1, 1, 1))), emit=accent,
                         strength=0.12 * t ** 3)
                  if n else cap_dark), bevel=0.06)
            glow = material(f"glow_{key}_{r}_{x}", hot, emit=hot, strength=1.5 + 3.0 * t ** 2) if n else legend_dim
            if legend:
                bpy.ops.object.text_add(location=(cx - 0.0, cy, hgt + 0.001))
                tx = bpy.context.object
                tx.data.body = legend
                tx.data.font = font
                tx.data.size = 0.42 if len(legend) == 1 else 0.24
                tx.data.align_x, tx.data.align_y = "CENTER", "CENTER"
                tx.data.materials.append(glow)
            if n:                                           # under-glow ring on the plate
                cube(f"ug_{key}_{r}_{x}", (cx, cy, 0.01), (wu * U - gap + 0.06, U - gap + 0.06, 0.02),
                     material(f"ugm_{key}_{r}_{x}", accent, emit=accent, strength=0.1 + 0.9 * t ** 2))
            x += wu * U
        width = max(width, x)
        y -= U
    grid_floor(pal)                                        # no plate: the glass keys sit right on the 1u grid
    return width, -y


def setup(pal, w, d, samples, scale):
    sc = bpy.context.scene
    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = 72
    cam_d.dof.use_dof = True
    cam_d.dof.aperture_fstop = 2.2
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    target = Vector((w * 0.52, -d * 0.52, 0.3))
    cam.location = target + Vector((-9.0, -24.0, 30.0))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam_d.dof.focus_distance = (target - cam.location).length
    sc.camera = cam

    def area(loc, size, energy, color):
        ld = bpy.data.lights.new("a", "AREA")
        ld.size, ld.energy, ld.color = size, energy, color
        ob = bpy.data.objects.new("a", ld)
        sc.collection.objects.link(ob)
        ob.location = loc
        ob.rotation_euler = (target - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    area(target + Vector((-16, 5, 7)), 8, 2600, (1, 1, 1))                       # raking key from the far left
    area(target + Vector((8, -12, 14)), 12, 700, lin(pal.get("blue", pal["accent"]))[:3])
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = lin(pal["background"])
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.4
    sc.world = world
    r = sc.render
    r.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.transmission_bounces = 12
    sc.cycles.max_bounces = 16
    r.resolution_x, r.resolution_y, r.resolution_percentage = 3840, 2160, scale
    sc.view_settings.view_transform = "AgX"


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheme", default="omarchy")
    ap.add_argument("--samples", type=int, default=96)
    ap.add_argument("--scale", type=int, default=100)
    args = ap.parse_args(argv)
    per_key, total = bindings()
    print(f"{total} bindings on {len([k for k in per_key if k not in MODS])} keys; top: {per_key.most_common(8)}")
    for name in (SCHEMES if args.scheme == "all" else [args.scheme]):
        pal = palettes.load()[name]
        bpy.ops.wm.read_factory_settings(use_empty=True)
        w, d = build(pal, per_key)
        setup(pal, w, d, args.samples, args.scale)
        out = OUT / f"keymap--{name}.png" if args.scale == 100 else ROOT / ".wip" / f"keymap--{name}@{args.scale}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        bpy.context.scene.render.filepath = str(out)
        bpy.ops.render.render(write_still=True)
        print("wrote", out)


main()
