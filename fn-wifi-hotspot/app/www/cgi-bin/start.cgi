#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"

load_cfg
validate_cfg || http_err "400 Bad Request" "invalid config"

# Best-effort cleanup of old allow-port rules (in case previous stop didn't run)
remove_allow_ports

# Best-effort: ensure uplink device is connected when explicitly selected.
if [ -n "${UPLINK_IFACE:-}" ]; then
  nmcli dev connect "$UPLINK_IFACE" >/dev/null 2>&1 || true
fi

if ! require_wifi_iface; then
  list="$(wifi_ifaces | tr '\n' ' ' | sed 's/ *$//')"
  if [ -z "$list" ]; then
    http_err "400 Bad Request" "No Wi-Fi device found. Check 'nmcli dev status'."
  else
    http_err "400 Bad Request" "Device '${IFACE:-}' is not a Wi-Fi device. Wi-Fi devices: $list"
  fi
fi

# 已有 connection 就 up；否则创建热点再尝试改名并 up
if nmcli -t -f NAME con show 2>/dev/null | grep -Fxq "$CONNECTION_NAME"; then
  # Apply optional IP/CIDR for shared network.
  if [ -n "${IP_CIDR:-}" ]; then
    nmcli con mod "$CONNECTION_NAME" ipv4.method shared ipv4.addresses "$IP_CIDR" >/dev/null 2>&1 || true
  fi
  out="$(nmcli con up id "$CONNECTION_NAME" 2>&1 || true)"
else
  out="$(nmcli dev wifi hotspot ifname "$IFACE" ssid "$SSID" password "$PASSWORD" band "$BAND" channel "$CHANNEL" 2>&1 || true)"
  nmcli con mod Hotspot connection.id "$CONNECTION_NAME" >/dev/null 2>&1 || true
  # Apply optional IP/CIDR for shared network.
  if [ -n "${IP_CIDR:-}" ]; then
    nmcli con mod "$CONNECTION_NAME" ipv4.method shared ipv4.addresses "$IP_CIDR" >/dev/null 2>&1 || true
  fi
  nmcli con up id "$CONNECTION_NAME" >/dev/null 2>&1 || true
fi

# Best-effort: ensure hotspot clients can reach internet.
# Some environments don't set up NAT automatically.
apply_hotspot_nat "$IFACE" "${UPLINK_IFACE:-}"

# Best-effort: allow hotspot clients to access host services on selected ports.
apply_allow_ports "$IFACE" "${ALLOW_PORTS:-}"

http_json
printf '{ "ok": true, "output": "%s" }\n' "$(json_escape "$out")"
