#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"

http_json

# Output schema:
# { "ok": true, "uplinks": ["eth0", "wwan0", ...] }
if ! command -v nmcli >/dev/null 2>&1; then
  printf '{ "ok": true, "uplinks": [] }\n'
  exit 0
fi

# List non-loopback, non-p2p devices.
# Filter out common virtual devices that are almost never valid uplinks.
devs="$(nmcli -t -f DEVICE dev status 2>/dev/null \
  | sed '/^$/d' \
  | awk '!/^lo$/' \
  | awk '!/^p2p/' \
  | awk '!/^(veth|docker|br-|virbr|vnet|tap|tun|wg|zt|tailscale|vboxnet|vmnet)/' \
  || true)"

printf '{ "ok": true, "uplinks": ['
first=1
printf '%s' "$devs" | while IFS= read -r dev; do
  [ -n "$dev" ] || continue
  if [ $first -eq 1 ]; then first=0; else printf ','; fi
  printf '"%s"' "$(json_escape "$dev")"
done
printf '] }\n'
