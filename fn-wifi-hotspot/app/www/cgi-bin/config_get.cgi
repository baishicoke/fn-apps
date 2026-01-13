#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"

STEP="init"
cgi_install_trap

load_cfg
# If caller provided a countryCode via query string, try to temporarily apply it
# to fetch channel options for that regulatory domain without persisting change.
req_cc="$(form_get countryCode "${QUERY_STRING:-}")"
orig_regdom="$(iw_reg_country)"
if [ -n "${req_cc:-}" ]; then
  # Try to set requested regdom; ignore failures and fall back to current regdom.
  iw reg set "${req_cc}" >/dev/null 2>&1 || true
fi

regdom="$(iw_reg_country)"
ch_bg="$(iw_channels_for_band bg || true)"
ch_a="$(iw_channels_for_band a || true)"

# Restore original regdom if we temporarily changed it
if [ -n "${req_cc:-}" ] && [ "${regdom:-}" != "${orig_regdom:-}" ]; then
  iw reg set "${orig_regdom:-00}" >/dev/null 2>&1 || true
fi

http_ok_begin

json_begin_named_object "config"
json_kv_string "iface" "$IFACE"
json_kv_string "uplinkIface" "$UPLINK_IFACE"
json_kv_string "ipCidr" "$IP_CIDR"
json_kv_string "allowPorts" "$ALLOW_PORTS"
json_kv_string "ssid" "$SSID"
json_kv_string "password" "$PASSWORD"
json_kv_string "countryCode" "$COUNTRY"
json_kv_string "band" "$BAND"
json_kv_string "channel" "$CHANNEL"
json_kv_string "channelWidth" "$CHANNEL_WIDTH"
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
