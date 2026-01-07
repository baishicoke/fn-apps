#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"

load_cfg
ensure_iface

# Best-effort cleanup of NAT rules (if we added them)
remove_hotspot_nat

# Best-effort cleanup of allow-port rules (if we added them)
remove_allow_ports

out1="$(nmcli con down id "$CONNECTION_NAME" 2>&1 || true)"
out2="$(nmcli dev disconnect "$IFACE" 2>&1 || true)"

http_json
printf '{ "ok": true, "output": "%s" }\n' "$(json_escape "$out1$out2")"
