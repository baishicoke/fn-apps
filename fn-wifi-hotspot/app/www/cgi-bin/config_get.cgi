#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"

load_cfg
http_json
printf '{ "ok": true, "config": {'
printf '"connectionName":"%s",' "$(json_escape "$CONNECTION_NAME")"
printf '"iface":"%s",' "$(json_escape "$IFACE")"
printf '"uplinkIface":"%s",' "$(json_escape "$UPLINK_IFACE")"
printf '"ipCidr":"%s",' "$(json_escape "$IP_CIDR")"
printf '"allowPorts":"%s",' "$(json_escape "$ALLOW_PORTS")"
printf '"ssid":"%s",' "$(json_escape "$SSID")"
printf '"password":"%s",' "$(json_escape "$PASSWORD")"
printf '"band":"%s",' "$(json_escape "$BAND")"
printf '"channel":%s' "$(json_escape "$CHANNEL")"
printf '} }\n'
