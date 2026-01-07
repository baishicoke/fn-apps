#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"

body="$(read_body)"

load_cfg
CONNECTION_NAME="$(form_get connectionName "$body")"
IFACE="$(form_get iface "$body")"
UPLINK_IFACE="$(form_get uplinkIface "$body")"
IP_CIDR="$(form_get ipCidr "$body")"
ALLOW_PORTS="$(form_get allowPorts "$body")"
SSID="$(form_get ssid "$body")"
PASSWORD="$(form_get password "$body")"
BAND="$(form_get band "$body")"
CHANNEL="$(form_get channel "$body")"

# UI only keeps one name field (SSID). If connectionName is not provided,
# use SSID as the connection id to keep things user-aligned.
if [ -z "${CONNECTION_NAME:-}" ]; then
  CONNECTION_NAME="$SSID"
fi

# Option B: persist a concrete iface even if client submits empty.
ensure_iface

validate_cfg || http_err "400 Bad Request" "invalid config (password>=8, band=bg|a, channel=number)"

save_cfg || http_err "500 Internal Server Error" "save config failed (CFG_FILE not writable)"
http_json
printf '{ "ok": true }\n'
