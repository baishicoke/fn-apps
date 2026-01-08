#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"

STEP="init"
cgi_install_trap

load_cfg
regdom="$(iw_reg_country)"
ch_bg="$(iw_channels_for_band bg || true)"
ch_a="$(iw_channels_for_band a || true)"

http_ok_begin

json_begin_named_object "config"
json_kv_string "connectionName" "$CONNECTION_NAME"
json_kv_string "iface" "$IFACE"
json_kv_string "uplinkIface" "$UPLINK_IFACE"
json_kv_string "ipCidr" "$IP_CIDR"
json_kv_string "allowPorts" "$ALLOW_PORTS"
json_kv_string "ssid" "$SSID"
json_kv_string "password" "$PASSWORD"
json_kv_string "band" "$BAND"
json_kv_string "channel" "$CHANNEL"
json_end

json_kv_string "regdom" "${regdom:-}"

json_begin_named_object "channelOptions"

json_begin_named_array "bg"
while IFS= read -r ch; do
  [ -n "${ch:-}" ] || continue
  json_arr_add_string "$ch"
done <<EOF
$ch_bg
EOF
json_end

json_begin_named_array "a"
while IFS= read -r ch; do
  [ -n "${ch:-}" ] || continue
  json_arr_add_string "$ch"
done <<EOF
$ch_a
EOF
json_end

json_end

http_ok_end
