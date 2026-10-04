# GIMP 3 Python-Fu batch script: neon glow composite.
# Run via: gimp -i --quit --batch-interpreter python-fu-eval -b "exec(open('glow.py').read())"
# Env: WP_BASE (background png), WP_LOGO (logo on black png), WP_OUT, WP_SCALE
import os

from gi.repository import Gimp, Gio

RUN = Gimp.RunMode.NONINTERACTIVE
scale = float(os.environ.get("WP_SCALE", "1"))

img = Gimp.file_load(RUN, Gio.File.new_for_path(os.environ["WP_BASE"]))
logo = Gimp.file_load_layer(RUN, img, Gio.File.new_for_path(os.environ["WP_LOGO"]))
img.insert_layer(logo, None, 0)
logo.set_mode(Gimp.LayerMode.SCREEN)  # logo is on opaque black: screen keeps only the light


def glow_layer(sigma, mode, opacity):
    layer = logo.copy()
    img.insert_layer(layer, None, 1)  # just under the crisp logo
    blur = Gimp.DrawableFilter.new(layer, "gegl:gaussian-blur", "glow")
    cfg = blur.get_config()
    cfg.set_property("std-dev-x", sigma * scale)
    cfg.set_property("std-dev-y", sigma * scale)
    blur.update()
    layer.merge_filter(blur)
    layer.set_mode(mode)
    layer.set_opacity(opacity)
    return layer


glow_layer(70.0, Gimp.LayerMode.SCREEN, 75.0)   # wide bloom
glow_layer(14.0, Gimp.LayerMode.ADDITION, 35.0)  # tight neon edge

flat = img.flatten()
Gimp.file_save(RUN, img, Gio.File.new_for_path(os.environ["WP_OUT"]), None)
img.delete()
