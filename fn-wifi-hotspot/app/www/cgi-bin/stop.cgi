#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"

STEP="init"
cgi_install_trap

load_cfg
ensure_iface

# Prefer runtime hotspot iface (may be a virtual AP iface).
load_nat_state
hotspot_iface="${HOTSPOT_IFACE:-$IFACE}"
virtual_iface="${HOTSPOT_VIRTUAL_IFACE:-}"

# Best-effort cleanup of NAT rules (if we added them)
remove_hotspot_nat

# Best-effort cleanup of allow-port rules (if we added them)
remove_allow_ports

out1="$(nmcli con down id "$CONNECTION_NAME" 2>&1 || true)"
out2="$(nmcli dev disconnect "$hotspot_iface" 2>&1 || true)"

out="${out1:-}${out2:-}"
if [ -n "${out1:-}" ] && [ -n "${out2:-}" ]; then
  out="$out1
$out2"
fi

# If we created a virtual AP iface, delete it.
if [ -n "${virtual_iface:-}" ] && [ "$virtual_iface" != "$IFACE" ]; then
  delete_iface "$virtual_iface"
fi

# Persist disabled state
write_hotspot_state 0

http_ok_output "$out"
