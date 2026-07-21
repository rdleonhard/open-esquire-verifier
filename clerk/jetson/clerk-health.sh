#!/bin/bash
# Health monitor for the Jetson Clerk host. Runs on a timer.
#
# Pushes an alert to the operator (ntfy) ONLY on state changes, so no spam:
#   - the Clerk stops responding (or comes back)
#   - CourtListener free-tier budget is spent / refreshed (at capacity)
#   - the SoC runs hot  -> drop to 7W eco ("low power when it needs it")
#     and restore 15W when it cools
#   - a disk fills up
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
source /mnt/ssd/clerk-data/clerk.env 2>/dev/null || true
STATE=/mnt/ssd/clerk-data/health.state
CLERK_URL="${CLERK_URL:-http://localhost:8454}"
TEMP_HOT=${TEMP_HOT:-80}      # C: drop to eco at/above this
TEMP_OK=${TEMP_OK:-70}        # C: restore balanced at/below this
DISK_PCT=${DISK_PCT:-90}

notify(){ "$DIR/clerk-notify.sh" "$1" "${2:-default}" "${3:-scales}"; }
get(){ grep -E "^$1=" "$STATE" 2>/dev/null | cut -d= -f2-; }
put(){ touch "$STATE"; { grep -v -E "^$1=" "$STATE" 2>/dev/null; echo "$1=$2"; } > "$STATE.tmp"; mv "$STATE.tmp" "$STATE"; }
changed(){ [ "$(get "$1")" != "$2" ]; }

# 1) is the Clerk answering?
if curl -s -m 8 "$CLERK_URL/status" -o /tmp/clerk.status.json 2>/dev/null; then up=yes; else up=no; fi
if changed up "$up"; then
  [ "$up" = no ] && notify "Clerk is DOWN — /status is not responding on the Jetson." urgent rotating_light
  [ "$up" = yes ] && [ -n "$(get seen)" ] && notify "Clerk is back up." default white_check_mark
  put up "$up"
fi
put seen 1

# 2) at CourtListener capacity?
if [ "$up" = yes ]; then
  cap=$(python3 -c "import json;print(json.load(open('/tmp/clerk.status.json')).get('at_capacity'))" 2>/dev/null)
  if changed cap "$cap"; then
    [ "$cap" = True ] && notify "Clerk AT CAPACITY — CourtListener free-tier budget spent; cached citations still answer." high hourglass
    [ "$cap" = False ] && [ -n "$(get seencap)" ] && notify "Clerk budget refreshed — answering freely again." default white_check_mark
    put cap "$cap"; put seencap 1
  fi
fi

# 3) temperature -> low power when it needs it
milli=$(cat /sys/devices/virtual/thermal/thermal_zone*/temp 2>/dev/null | sort -n | tail -1)
temp=$(( ${milli:-0} / 1000 ))
mode=$(nvpmodel -q 2>/dev/null | grep -oE "[0-9]+$" | tail -1)
if [ "$temp" -ge "$TEMP_HOT" ] && [ "$mode" != "3" ]; then
  nvpmodel -m 3 >/dev/null 2>&1
  notify "SoC ${temp}C — dropped to 7W eco to cool down." high fire
  put thermal eco
elif [ "$temp" -le "$TEMP_OK" ] && [ "$(get thermal)" = eco ]; then
  nvpmodel -m 0 >/dev/null 2>&1
  notify "SoC ${temp}C — restored 15W balanced." default snowflake
  put thermal ""
fi

# 4) disks
for m in / /mnt/ssd; do
  pct=$(df --output=pcent "$m" 2>/dev/null | tail -1 | tr -dc 0-9)
  key="disk_${m//\//_}"
  if [ -n "$pct" ] && [ "$pct" -ge "$DISK_PCT" ]; then
    changed "$key" full && notify "Disk $m at ${pct}% on the Jetson." high floppy_disk
    put "$key" full
  else
    put "$key" ok
  fi
done
