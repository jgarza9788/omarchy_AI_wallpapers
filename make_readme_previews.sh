#!/usr/bin/env bash
# Small JPG previews for the README (the 4K PNGs stay in output/):
#   docs/hero.jpg            a 4x3 mosaic of favourites
#   docs/thumbs/NN-name.jpg  one representative per design
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p docs/thumbs
PICKS=(
  01-monolith/monolith--matte-black      02-topography/topography--kanagawa   03-glyph-rain/glyph-rain--hackerman
  04-pixel-dusk/pixel-dusk--ethereal     05-bauhaus-grid/bauhaus-grid--rose-pine 06-suminagashi/suminagashi--rose-pine
  07-galaxy/galaxy--ethereal             08-shroud/shroud--rose-pine          09-sigils/sigil--lumon
  10-sundial/sundial--09h                11-app-galaxy/app-galaxy--omarchy    12-3d-rotation/rotation--tokyo-night
  13-event-horizon/event-horizon--matte-black 14-collapse/collapse--nord      15-wake/wake--catppuccin
  16-merger/merger--tokyo-night          17-lightspeed/lightspeed--hackerman  18-swatches/swatches--gruvbox
  19-groovy/groovy--ristretto            20-halftone/halftone--vantablack     21-night-side/night-side--tokyo-night
  22-paper-terrain/paper-terrain--rose-pine 23-oma-blend/oma-icon-wall--omarchy 24-oma-dome/oma-dome--mirror
  25-twist/twist--glass                  15.1-wake/wake-straight--omarchy
  26-strata/strata--gruvbox             27-physarum/physarum--omarchy        28-chladni/chladni--omarchy
  29-keymap/keymap--omarchy              30-caustics/caustics--osaka-jade     31-loupe/loupe--omarchy
  32-periodic/periodic--omarchy          33-city/city--omarchy                34-bubbles/bubbles--catppuccin
  36-character-sheet/sheet-knight--omarchy  37-character-sheet/sketch-wizard--omarchy
  38-gel/gel--omarchy  39-shell-metro/metro--omarchy  40-sampler/sampler--omarchy
  35-receipt/receipt--gruvbox
  41-prism/prism--omarchy  42-neon/neon--omarchy  43-ferrofluid/ferrofluid--omarchy  44-shatter/shatter--omarchy
  45-tornado/tornado--omarchy  46-shockwave/shockwave--omarchy  47-disturbed-code/code-lens--tokyo-night
)
for p in "${PICKS[@]}"; do
  [ -f "output/$p.png" ] || { echo "skip $p (not rendered)"; continue; }
  magick "output/$p.png" -resize 960x540 -strip -quality 82 "docs/thumbs/${p%%/*}.jpg"
done
HERO=(13-event-horizon 24-oma-dome 06-suminagashi 19-groovy
      23-oma-blend 11-app-galaxy 04-pixel-dusk 21-night-side
      12-3d-rotation 15-wake 09-sigils 25-twist)
magick montage $(printf 'docs/thumbs/%s.jpg ' "${HERO[@]}") -geometry 480x270+4+4 -tile 4x \
  -background '#0e0e14' -strip -quality 84 docs/hero.jpg
echo "previews in docs/"
