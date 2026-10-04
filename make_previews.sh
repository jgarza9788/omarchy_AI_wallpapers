#!/usr/bin/env bash
# Contact sheet per wallpaper + one gallery of everything -> output/_previews/
set -euo pipefail
cd "$(dirname "$0")"
FONT=assets/fonts/SpaceMono/SpaceMonoNerdFontMono-Regular.ttf
mkdir -p output/_previews

for dir in output/[0-9][0-9]-*/; do
  name=$(basename "$dir")
  files=("$dir"*.png)
  [ -e "${files[0]}" ] || continue
  cols=3; [ "${#files[@]}" -gt 9 ] && cols=6   # sundial: 24 hourly frames
  magick montage -label '%t' "${files[@]}" -font "$FONT" -pointsize 22 -fill '#cccccc' \
    -geometry 768x432+16+16 -tile "${cols}x" -background '#111111' -depth 8 \
    -title "$name" "output/_previews/$name.png"
  echo "sheet output/_previews/$name.png"
done

# gallery: every scheme of every design, but only 5 sample hours of the sundial
mapfile -t all < <(ls output/[0-9][0-9]-*/*.png | grep -v '/10-sundial/')
all+=(output/10-sundial/sundial--{07,10,13,17,22}h.png)
magick montage -label '%t' "${all[@]}" -font "$FONT" -pointsize 16 -fill '#cccccc' \
  -geometry 480x270+10+10 -tile 5x -background '#111111' -depth 8 \
  output/_previews/gallery.png
echo "gallery output/_previews/gallery.png"
