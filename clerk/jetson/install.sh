#!/bin/bash
# Install the Clerk as a full-time service on the Jetson Orin Nano Super,
# with health alerts and power management. Secrets come from the environment
# (never the repo). Run as root:
#
#   sudo COURTLISTENER_TOKEN=xxxx NTFY_TOPIC=yyyy bash install.sh
#
# Rerunnable. Keeps an existing clerk.env if present.
set -euo pipefail
REPO=/mnt/ssd/open-esquire-verifier
JD="$REPO/clerk/jetson"
DATA=/mnt/ssd/clerk-data
ENVF="$DATA/clerk.env"
OWNER="${SUDO_USER:-rob}"

mkdir -p "$DATA"
if [ ! -f "$ENVF" ]; then
  umask 077
  cat > "$ENVF" <<EOF
COURTLISTENER_TOKEN=${COURTLISTENER_TOKEN:-}
NTFY_URL=${NTFY_URL:-https://ntfy.sh}
NTFY_TOPIC=${NTFY_TOPIC:-}
CLERK_URL=http://localhost:8454
CLERK_HOST=0.0.0.0
CLERK_PORT=8454
CLERK_DATA_DIR=$DATA
EOF
  chown "$OWNER" "$ENVF"; chmod 600 "$ENVF"
  echo "wrote $ENVF"
else
  echo "$ENVF exists — keeping it (edit by hand to change secrets)"
fi
chown -R "$OWNER" "$DATA"

install -m 755 "$JD/clerk-power" /usr/local/bin/clerk-power
chmod +x "$JD"/clerk-notify.sh "$JD"/clerk-health.sh

for u in clerk.service clerk-health.service clerk-health.timer \
         clerk-alert@.service clerk-boot-notify.service clerk-power.service; do
  install -m 644 "$JD/$u" "/etc/systemd/system/$u"
done

systemctl daemon-reload
systemctl enable --now clerk-power.service
systemctl enable --now clerk.service
systemctl enable --now clerk-health.timer
systemctl enable clerk-boot-notify.service
echo
echo "installed. power: $(clerk-power status | tail -1)"
systemctl --no-pager --lines=0 status clerk.service | head -4
