#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"

http_json

# List Wi-Fi interfaces if nmcli is available.
# Output schema:
# { "ok": true, "ifaces": ["wlp2s0", ...] }
ifaces="$(wifi_ifaces 2>/dev/null || true)"

printf '{ "ok": true, "ifaces": ['
first=1
printf '%s' "$ifaces" | while IFS= read -r dev; do
  [ -n "$dev" ] || continue
  if [ $first -eq 1 ]; then first=0; else printf ','; fi
  printf '"%s"' "$(json_escape "$dev")"
done
printf '] }\n'
