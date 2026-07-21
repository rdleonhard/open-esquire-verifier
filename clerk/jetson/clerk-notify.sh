#!/bin/bash
# Push a message to the operator via ntfy (free, no account).
#   clerk-notify.sh "message" [priority] [tags]
# The private topic + url live in clerk.env (off the repo).
source /mnt/ssd/clerk-data/clerk.env 2>/dev/null || true
[ -z "${NTFY_TOPIC:-}" ] && exit 0
curl -s -m 10 \
  -H "Title: Open Esquire Clerk (Jetson)" \
  -H "Priority: ${2:-default}" \
  -H "Tags: ${3:-scales}" \
  -d "$1" "${NTFY_URL:-https://ntfy.sh}/$NTFY_TOPIC" >/dev/null 2>&1 || true
