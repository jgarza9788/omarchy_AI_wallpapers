#!/usr/bin/env bash
# Rebuild every wallpaper in every colour scheme (3840x2160), then the previews.
# The Blender renders (01, 08, 12) are by far the slowest: 10-25 min per scheme on CPU.
#   ./build_all.sh            everything
#   ./build_all.sh --fast     skip the Blender pieces
set -euo pipefail
cd "$(dirname "$0")"

python3 palettes/palettes.py >/dev/null
python3 src/02-topography/topography.py
python3 src/03-glyph-rain/glyph_rain.py
python3 src/04-pixel-dusk/pixel_dusk.py
python3 src/05-bauhaus-grid/bauhaus_grid.py
python3 src/06-suminagashi/suminagashi.py
python3 src/07-galaxy/galaxy.py
python3 src/09-sigils/sigils.py
python3 src/10-sundial/sundial.py
python3 src/11-app-galaxy/app_galaxy.py
python3 src/15.1-wake/wake_straight.py   # renders its interceptor sprite with Blender first
python3 src/26-strata/strata.py
python3 src/27-physarum/physarum.py
python3 src/28-chladni/chladni.py
python3 src/30-caustics/caustics.py
python3 src/inventory.py --refresh   # 32-37 read the installed-software inventory
python3 src/github_stats.py --refresh || true   # 36-37: GitHub stats via gh (optional)
python3 src/32-periodic/periodic.py
python3 src/34-bubbles/bubbles.py
python3 src/35-receipt/receipt.py
python3 src/36-character-sheet/character_sheet.py
python3 src/37-character-sheet/sketch_sheet.py
python3 src/38-gel/gel.py
python3 src/39-shell-metro/shell_metro.py   # reads ~/.bash_history
python3 src/40-sampler/sampler.py
python3 src/45-tornado/tornado.py
python3 src/46-shockwave/shockwave.py
python3 src/47-disturbed-code/disturbed_code.py
for g in 11-app-galaxy/app_galaxy 13-event-horizon/event_horizon 14-collapse/collapse 15-wake/wake 16-merger/merger \
         17-lightspeed/lightspeed 22-paper-terrain/paper_terrain; do
  python3 "src/$g.py" --scheme omarchy   # official brand colours
done
for g in 13-event-horizon/event_horizon 14-collapse/collapse 15-wake/wake 16-merger/merger 17-lightspeed/lightspeed \
         18-swatches/swatches 19-groovy/groovy 21-night-side/night_side 22-paper-terrain/paper_terrain; do
  python3 "src/$g.py"
done
if [[ "${1:-}" != "--fast" ]]; then
  blender -b -P src/01-monolith/monolith.py -- --scheme all
  blender -b -P src/08-shroud/shroud.py -- --scheme all
  blender -b -P src/12-3d-rotation/rotation.py -- --scheme all --samples 48
  python3 src/20-halftone/halftone.py   # re-screens the 01/08 Blender renders
  blender -b -P src/23-oma-blend/oma_blend.py -- --layout grid --scheme omarchy --samples 48
  blender -b assets/OMA.blend -P src/23-oma-blend/oma_icon_wall.py -- --scheme omarchy
  blender -b assets/OMA_00.blend -P src/24-oma-dome/oma_dome.py -- --variant all
  blender -b assets/OMA_01.blend -P src/25-twist/twist.py -- --variant all
  blender -b -P src/29-keymap/keymap.py -- --scheme all --samples 64
  blender -b -P src/31-loupe/loupe.py -- --scheme all
  blender -b -P src/31-loupe/loupe.py -- --scheme omarchy --glass all
  blender -b -P src/33-city/city.py -- --scheme all
  for d in 41-prism/prism 42-neon/neon 43-ferrofluid/ferrofluid 44-shatter/shatter; do
    blender -b -P "src/$d.py" -- --scheme all --samples 64
  done
fi
./make_previews.sh
