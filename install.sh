#!/usr/bin/env bash
# Copy each wallpaper into the Omarchy user-backgrounds folder of the theme it was made for:
#   output/*/<design>--<theme>.png -> ~/.config/omarchy/backgrounds/<theme>/
# They then show up when cycling backgrounds (omarchy-theme-bg-next) in that theme.
set -euo pipefail
cd "$(dirname "$0")"
for f in output/[01]*/*.png; do
  [[ $f == */10-sundial/* ]] && continue  # hourly frames, see README
  theme=$(basename "$f" .png); theme=${theme##*--}
  dest="$HOME/.config/omarchy/backgrounds/$theme"
  mkdir -p "$dest" && cp "$f" "$dest/" && echo "$f -> $dest/"
done
