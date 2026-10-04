#!/usr/bin/env bash
# Show the Sundial frame for the current hour. Run it hourly, e.g. from a systemd
# user timer (see sundial.timer / sundial.service next to this script) or cron.
set -euo pipefail
frames="$(cd "$(dirname "$0")/../.." && pwd)/output/10-sundial"
omarchy-theme-bg-set "$frames/sundial--$(date +%H)h.png"
