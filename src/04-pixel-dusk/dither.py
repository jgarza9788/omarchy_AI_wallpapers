# GIMP 3 Python-Fu batch script: dither to a custom palette, then nearest-neighbour upscale.
# Run via: gimp -i --quit --batch-interpreter python-fu-eval -b "exec(open('dither.py').read())"
# Env: WP_IN, WP_OUT, WP_DITHER (FS|FS_LOWBLEED|FIXED|NONE), WP_COLORS (comma-separated hex), WP_W, WP_H, WP_NAME (temp palette name)
import os

from gi.repository import Gegl, Gimp, Gio

RUN = Gimp.RunMode.NONINTERACTIVE

img = Gimp.file_load(RUN, Gio.File.new_for_path(os.environ["WP_IN"]))

palette = Gimp.Palette.new(os.environ["WP_NAME"])
for i, hx in enumerate(os.environ["WP_COLORS"].split(",")):
    color = Gegl.Color.new(hx)
    palette.add_entry(f"c{i}", color)

img.convert_indexed(getattr(Gimp.ConvertDitherType, os.environ.get("WP_DITHER", "FIXED")), Gimp.ConvertPaletteType.CUSTOM,
                    0, False, False, palette.get_name())
img.convert_rgb()

Gimp.context_set_interpolation(Gimp.InterpolationType.NONE)
img.scale(int(os.environ["WP_W"]), int(os.environ["WP_H"]))

Gimp.file_save(RUN, img, Gio.File.new_for_path(os.environ["WP_OUT"]), None)
palette.delete()
img.delete()
