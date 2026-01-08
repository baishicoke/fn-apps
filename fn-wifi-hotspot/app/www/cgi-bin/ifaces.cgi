#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"

STEP="init"
cgi_install_trap

# List Wi-Fi interfaces if nmcli is available.
# Output schema:
# { "ok": true, "ifaces": ["wlp2s0", ...] }
ifaces="$(wifi_ifaces 2>/dev/null || true)"

http_ok_begin
json_begin_named_array "ifaces"
while IFS= read -r dev; do
  [ -n "${dev:-}" ] || continue
  json_arr_add_string "$dev"
done <<EOF
$ifaces
EOF
json_end
http_ok_end
