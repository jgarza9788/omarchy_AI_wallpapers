---
name: omarchy-wallpapers
description: Create, remix or re-render 4K Omarchy desktop wallpapers in this repo (numpy/ImageMagick generators, GIMP batch, Blender/Cycles scenes, Omarchy theme palettes). Use when asked to make a new wallpaper design, add color variants, render the official "omarchy" scheme, work with assets/*.blend, or refresh the README previews.
---

# Omarchy wallpapers

Each design lives in `src/NN-name/` and writes 3840×2160 PNGs to `output/NN-name/<name>--<scheme>.png`.
Read `README.md` for what exists; pick the next free number for a new design.

## Conventions
- **Palettes**: `palettes/palettes.py` reads `/usr/share/omarchy/themes/*/colors.toml` → `palettes.json`.
  Keys: `background foreground accent darker_background dark_foreground` + ANSI names (`red green yellow blue magenta cyan …`).
  `omarchy` is the official brand scheme: Tokyo Night + accent `#9ece6a`, plus `oma_bands` (the 5 OMA logo greens, light→dark).
  Always pick colors from the palette; filter `pal.items()` to string values (since `oma_bands` is a list).
- **2D generators** use `src/common.py`: `scheme_args(SCHEMES)` gives `--scheme <theme|all>` and `--scale` (previews);
  `out_path(folder, stem, scale)` sends `scale != 1` to `.wip/` (scratch) and full size to `output/`;
  `save_rgb(img, path, post)` writes a float RGB array via ImageMagick (with TPDF dither, which prevents 8-bit banding)
  and `post` takes extra magick ops (text, wordmark). Icon work goes through `src/appfield.py` (Atlas, Canvas.stamp/trail,
  affine warps, Camera, splat, finish, brand). Exact O/M/A logo outlines: `src/oma_shapes.py`.
- **Blender scripts** run `blender -b [file.blend] -P script.py -- --scheme X --samples N --scale PCT`. Use Cycles on the CPU
  (Intel iGPU), with denoising and AgX. A 4K render is 7–25 min, so test at `--scale 25 --samples 16–24` first.
- **Branding**: assets in `assets/brand/` (wordmark/logo/oma-logo, svg + 4096px png); fonts in `assets/fonts/`
  (Iosevka / SpaceMono / CaskaydiaCove / 3270 Nerd Font Mono).
- After adding a design: update `README.md`, `build_all.sh`, `PICKS` in `make_readme_previews.sh`, then run
  `./make_previews.sh` and `./make_readme_previews.sh`.

## Workflow
1. Render a 25–50% preview into `.wip/`, then **look at it** (Read the PNG) before rendering at 4K.
2. Iterate on composition and contrast, then run the full set in the background.
3. Check the 4K result (downscale or crop it) before reporting.

## Pitfalls already hit (don't repeat)
- Glass or chrome in front of black disappears. Give it something bright to bend or reflect (glowing icons, a soft emissive
  gradient behind it, specular-only softboxes with `visible_diffuse=False`). Flat glass seen dead-on is invisible, so turn it about 30°.
- Glossy walls reflect softboxes as blobs, so make backdrops purely diffuse.
- EEVEE `ShaderNodeEeveeSpecular` renders **black** in Cycles. EEVEE glass looks dark grey; switch to Cycles for real refraction.
- `assets/OMA_00.blend` / `OMA_01.blend` cameras use DOF at f/0.1; refocus (`dof.focus_distance`) if the subject moved.
- In the .blend files the camera looks toward +z from z=-4, with **screen-right = −x**.
- Emission strength over ~2 blows out to white under AgX, so keep brand greens saturated with strength ≈1.
- MNEE shadow caustics did not work on the flat-faced, arrayed OMA pieces.
- Never wait on a job with `pgrep -f '<pattern>'` from a shell whose own command line contains that pattern: it matches itself
  and waits forever. Match the process name instead (`pgrep -x blender`) or keep the PID.
- ImageMagick rejects `label:@file` by policy, so pass text inline. MVG draws of thousands of glyphs are extremely slow,
  so use the numpy glyph atlas.
- GIMP 3 batch: `gimp -i --quit --batch-interpreter python-fu-eval -b "exec(open(...).read())"` (without `--quit` it hangs).
