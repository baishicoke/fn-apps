#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"

STEP="init"
cgi_install_trap

load_cfg
STEP="validate"
validate_cfg || http_err "400 Bad Request" "${CFG_ERR:-invalid config}"

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

# Decide which iface actually runs the hotspot.
# Default: reuse IFACE (will interrupt any STA connection).
parent_iface="$IFACE"
hotspot_iface="$IFACE"
virtual_iface=""
notice=""

sta_prev_con=""
if command -v nmcli >/dev/null 2>&1; then
  sta_prev_con="$(nmcli -g GENERAL.CONNECTION dev show "$IFACE" 2>/dev/null | head -n1 || true)"
  case "$sta_prev_con" in "" | "--") sta_prev_con="" ;; esac
fi

if iw_supports_sta_ap; then
  virtual_iface="$(mk_ap_iface_name "$IFACE")"
  if ensure_virtual_ap_iface "$IFACE" "$virtual_iface"; then
    hotspot_iface="$virtual_iface"
    notice="Using virtual AP iface '$hotspot_iface' (STA on '$IFACE' kept)."
  else
    virtual_iface=""
    notice="Driver reports STA+AP support, but failed to create virtual AP iface; will disconnect STA and use '$IFACE'."
  fi
else
  if [ -n "${sta_prev_con:-}" ]; then
    notice="Adapter does not support STA+AP; disconnected '$sta_prev_con' on '$IFACE'."
  else
    notice="Adapter does not support STA+AP; hotspot will use '$IFACE' (may interrupt Wi-Fi)."
  fi
fi

# Do not use the same interface as both hotspot and uplink.
if [ -n "${UPLINK_IFACE:-}" ] && [ "$UPLINK_IFACE" = "$hotspot_iface" ]; then
  http_err "400 Bad Request" "uplinkIface cannot be the same as hotspot iface ($hotspot_iface). Choose another uplink interface or leave uplinkIface empty (auto)."
fi
if [ -n "${UPLINK_IFACE:-}" ] && [ "$UPLINK_IFACE" = "$IFACE" ] && [ "$hotspot_iface" = "$IFACE" ]; then
  http_err "400 Bad Request" "uplinkIface cannot be the same as hotspot iface ($IFACE) unless STA+AP concurrent mode is available."
fi

# Best-effort capability check: many Wi-Fi adapters cannot do AP/hotspot mode.
if command -v iw >/dev/null 2>&1; then
  if ! iw list 2>/dev/null | sed -n '/Supported interface modes:/,/^[[:space:]]*$/p' | grep -Eq '^[[:space:]]*\*[[:space:]]+AP\b'; then
    http_err "400 Bad Request" "Device '$IFACE' does not appear to support AP/hotspot mode (iw list has no '* AP'). Use another Wi-Fi adapter."
  fi
fi

# 如果已有同名连接：仅当它是热点(AP)连接时直接删除并重建；否则视为名字冲突。
if nmcli -t -f NAME con show 2>/dev/null | grep -Fxq "$CONNECTION_NAME"; then
  # Guard against conflicts: same connection name but not a hotspot/AP profile.
  con_type="$(nmcli -g connection.type con show "$CONNECTION_NAME" 2>/dev/null | head -n1 || true)"
  con_mode=""
  if [ "$con_type" = "802-11-wireless" ]; then
    con_mode="$(nmcli -g 802-11-wireless.mode con show "$CONNECTION_NAME" 2>/dev/null | head -n1 || true)"
  fi
  if [ "$con_type" != "802-11-wireless" ] || [ "$con_mode" != "ap" ]; then
    http_err "400 Bad Request" "Connection name conflict: '$CONNECTION_NAME' exists but is not a hotspot (type=${con_type:-unknown}, mode=${con_mode:-n/a}). Please choose another connectionName/SSID or rename the existing connection."
  fi

  # Always delete and recreate (avoid stale/partial profiles).
  nmcli con down id "$CONNECTION_NAME" >/dev/null 2>&1 || true
  nmcli con delete "$CONNECTION_NAME" >/dev/null 2>&1 || true

fi

out=""
# If we're not using a virtual AP iface, we must disconnect STA first.
if [ "$hotspot_iface" = "$IFACE" ]; then
  nmcli dev disconnect "$IFACE" >/dev/null 2>&1 || true
fi

if ! out="$(nmcli dev wifi hotspot ifname "$hotspot_iface" ssid "$SSID" password "$PASSWORD" band "$BAND" channel "$CHANNEL" 2>&1)"; then
  case "$out" in
    *802.1X\ supplicant\ took\ too\ long*)
      out="$out
Tips:
- If '$hotspot_iface' is currently connected to Wi-Fi, try disconnecting it first (nmcli dev disconnect $hotspot_iface).
- Some adapters/drivers cannot run hotspot/AP mode (check: iw list | sed -n '/Supported interface modes:/,/^\s*$/p').
- Check rfkill (rfkill list) and NetworkManager logs (journalctl -xe)."
      ;;
  esac
  http_err "500 Internal Server Error" "$out"
fi

# Discover the actual connection created/activated on the hotspot device.
hotspot_con="$(nmcli -g GENERAL.CONNECTION dev show "$hotspot_iface" 2>/dev/null | head -n1 || true)"
case "$hotspot_con" in
  "" | "--") hotspot_con="" ;;
esac
# Fallback (older NM): try the default name.
if [ -z "$hotspot_con" ]; then
  hotspot_con="Hotspot"
fi

# Rename hotspot connection to user-visible connectionName (and surface conflicts).
if [ "$hotspot_con" != "$CONNECTION_NAME" ]; then
  if ! nmcli con mod "$hotspot_con" connection.id "$CONNECTION_NAME" >/dev/null 2>&1; then
    http_err "400 Bad Request" "Connection name conflict: cannot rename hotspot connection '$hotspot_con' to '$CONNECTION_NAME'. Please choose another connectionName/SSID or rename the existing connection."
  fi
  hotspot_con="$CONNECTION_NAME"
fi
# Apply optional IP/CIDR for shared network.
if [ -n "${IP_CIDR:-}" ]; then
  nmcli con mod "$hotspot_con" ipv4.method shared ipv4.addresses "$IP_CIDR" >/dev/null 2>&1 || true
fi
if ! nmcli con up id "$hotspot_con" >/dev/null 2>&1; then
  http_err "500 Internal Server Error" "nmcli: failed to bring up hotspot connection '$hotspot_con'"
fi

# Best-effort: ensure hotspot clients can reach internet.
# Some environments don't set up NAT automatically.
apply_hotspot_nat "$hotspot_iface" "${UPLINK_IFACE:-}" "$parent_iface" "$virtual_iface"

# Best-effort: allow hotspot clients to access host services on selected ports.
apply_allow_ports "$hotspot_iface" "${ALLOW_PORTS:-}"

# Persist enabled state so we can restore after reboot.
write_hotspot_state 1

http_ok_output "$out" "${notice:-}"
