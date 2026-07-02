#!/bin/bash
# Sync attorney rulings from the CYD verifier's microSD to this repo and
# publish to GitHub Pages. Safe to run any time (no-op when nothing changed).
#
#   ./publish.sh              # pull from device, merge, commit, push
#   ./publish.sh --no-push    # merge locally only
#
# The device keeps the authoritative log (/sd/rulings.jsonl); this script
# merges the recent window (GET /log?n=50) into data/rulings.json by docket
# id, so running it at least once per ~50 rulings loses nothing.
set -euo pipefail
cd "$(dirname "$0")"

MAC="14:33:5c:b:65:54"          # Board A (Open Esquire verifier node)
CACHE="$HOME/.cyd_ip"

arp_lookup() { arp -an | awk -v m="$MAC" 'tolower($0) ~ m {gsub(/[()]/,"",$2); print $2; exit}'; }

ip=""
[ -f "$CACHE" ] && ip="$(cat "$CACHE")"
if [ -z "$ip" ] || ! curl -s -m 3 "http://$ip/api" >/dev/null 2>&1; then
  ip="$(arp_lookup)"
fi
[ -n "$ip" ] || { echo "verifier not found on the network" >&2; exit 2; }

curl -s -m 10 "http://$ip/log?n=50" | python3 - <<'EOF'
import json, sys, datetime, os

new = json.load(sys.stdin)
path = "data/rulings.json"
cur = {"rulings": []}
if os.path.exists(path):
    with open(path) as f:
        cur = json.load(f)

by_id = {r["id"]: r for r in cur.get("rulings", [])}
added = 0
for r in new.get("rulings", []):
    r.pop("raw", None)                  # touch coords stay private to the device
    if r["id"] not in by_id:
        added += 1
    by_id[r["id"]] = r

rulings = sorted(by_id.values(), key=lambda r: (r.get("date", ""), r.get("ruled", "")))
out = {
    "updated": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    "total": len(rulings),
    "rulings": rulings,
}
with open(path, "w") as f:
    json.dump(out, f, indent=1)
print("merged: %d new, %d total" % (added, len(rulings)))
EOF

if git diff --quiet -- data/rulings.json; then
  echo "no new rulings; nothing to publish"
  exit 0
fi

git add data/rulings.json
git commit -m "docket sync: $(date '+%Y-%m-%d %H:%M')" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" >/dev/null
if [ "${1:-}" != "--no-push" ]; then
  git push
  echo "published"
else
  echo "committed (not pushed)"
fi
