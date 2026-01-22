#!/bin/sh
# shellcheck disable=SC2034
set -eu
. "$(dirname "$0")/common.sh"

STEP="init"
cgi_install_trap

# Output schema:
# { "ok": true, "uplinks": ["eth0", "wlan0", ...] }
if ! command -v nmcli >/dev/null 2>&1; then
  http_ok_begin
  json_begin_named_array "uplinks"
  json_end
  http_ok_end
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

http_ok_begin
json_begin_named_array "uplinks"
while IFS= read -r dev; do
  [ -n "${dev:-}" ] || continue
  json_arr_add_string "$dev"
done <<EOF
$devs
EOF
json_end
http_ok_end
