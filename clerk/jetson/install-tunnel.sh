#!/bin/bash
# Expose the Clerk on the public internet with a Cloudflare *quick* tunnel:
# no Cloudflare account, no domain, no cost. The public URL is random and
# changes if the tunnel restarts; the health monitor pushes the new URL via
# ntfy, and the current one is always in /mnt/ssd/clerk-data/tunnel-url.txt.
#
#   sudo bash install-tunnel.sh
#
# To upgrade later to a stable branded address (e.g. clerk.openesquire.com),
# replace this with a named Cloudflare tunnel — see the README.
set -euo pipefail
REPO=/mnt/ssd/open-esquire-verifier
JD="$REPO/clerk/jetson"

if ! command -v cloudflared >/dev/null; then
  arch=$(dpkg --print-architecture)
  tmp=$(mktemp --suffix=.deb)
  echo "downloading cloudflared ($arch)..."
  curl -fsSL -o "$tmp" \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${arch}.deb"
  dpkg -i "$tmp"; rm -f "$tmp"
fi
cloudflared --version

install -m 644 "$JD/cloudflared-clerk.service" \
  /etc/systemd/system/cloudflared-clerk.service
systemctl daemon-reload
systemctl enable --now cloudflared-clerk.service

echo "waiting for the tunnel to come up..."
url=""
for _ in $(seq 1 25); do
  url=$(journalctl -u cloudflared-clerk --no-pager -o cat 2>/dev/null \
        | grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" | tail -1)
  [ -n "$url" ] && break
  sleep 2
done
if [ -n "$url" ]; then
  echo "$url" > /mnt/ssd/clerk-data/tunnel-url.txt
  echo "PUBLIC URL: $url"
else
  echo "tunnel not up yet; check: journalctl -u cloudflared-clerk -n 30"
fi
