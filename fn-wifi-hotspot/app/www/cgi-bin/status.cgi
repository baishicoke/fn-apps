#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"

load_cfg
ensure_iface

dev_line="$(nmcli -t -f DEVICE,STATE,CONNECTION dev status 2>/dev/null | grep "^${IFACE}:" || true)"
state="unknown"
active=""
if [ -n "$dev_line" ]; then
  state="$(printf '%s' "$dev_line" | cut -d: -f2)"
  active="$(printf '%s' "$dev_line" | cut -d: -f3-)"
fi

running="false"
[ "$active" = "$CONNECTION_NAME" ] && running="true"

ip="$(ip -4 addr show dev "$IFACE" 2>/dev/null | awk '/inet[[:space:]]/{print $2; exit}' || true)"

uplink_iface="${UPLINK_IFACE:-}"
if [ -z "$uplink_iface" ] && command -v ip >/dev/null 2>&1; then
  uplink_iface="$(ip route show default 2>/dev/null | awk '{for(i=1;i<=NF;i++){if($i=="dev"){print $(i+1); exit}}}' || true)"
fi

ip_forward=""
ip_forward_bool="false"
if command -v sysctl >/dev/null 2>&1; then
  ip_forward="$(sysctl -n net.ipv4.ip_forward 2>/dev/null | tr -d '\r' || true)"
  [ "$ip_forward" = "1" ] && ip_forward_bool="true"
fi

internet_ok="null"
internet_reason=""
internet_target="1.1.1.1"
route_dev=""
route_src=""
gateway=""
gateway_ok="null"
http_ok="null"
http_url="http://connectivitycheck.gstatic.com/generate_204"
if [ "$running" = "true" ]; then
  if command -v ip >/dev/null 2>&1; then
    route_line="$(ip -4 route get "$internet_target" 2>/dev/null | head -n1 || true)"
    if [ -n "$route_line" ]; then
      route_dev="$(printf '%s' "$route_line" | awk '{for(i=1;i<=NF;i++){if($i=="dev"){print $(i+1); exit}}}' || true)"
      route_src="$(printf '%s' "$route_line" | awk '{for(i=1;i<=NF;i++){if($i=="src"){print $(i+1); exit}}}' || true)"
    fi

    def_line="$(ip -4 route show default 2>/dev/null | head -n1 || true)"
    if [ -n "$def_line" ]; then
      gateway="$(printf '%s' "$def_line" | awk '{for(i=1;i<=NF;i++){if($i=="via"){print $(i+1); exit}}}' || true)"
    fi
  fi

  if command -v ping >/dev/null 2>&1; then
    probe_dev="${route_dev:-}"
    if [ -z "$probe_dev" ]; then
      probe_dev="${uplink_iface:-}"
    fi

    # Gateway reachability (helps explain failures).
    if [ -n "${gateway:-}" ]; then
      if [ -n "$probe_dev" ]; then
        if ping -c 1 -W 1 -I "$probe_dev" "$gateway" >/dev/null 2>&1; then
          gateway_ok="true"
        else
          gateway_ok="false"
        fi
      else
        if ping -c 1 -W 1 "$gateway" >/dev/null 2>&1; then
          gateway_ok="true"
        else
          gateway_ok="false"
        fi
      fi
    fi

    ping_ok="false"
    if [ -n "$probe_dev" ]; then
      if ping -c 1 -W 1 -I "$probe_dev" "$internet_target" >/dev/null 2>&1; then
        ping_ok="true"
      fi
    else
      if ping -c 1 -W 1 "$internet_target" >/dev/null 2>&1; then
        ping_ok="true"
      fi
    fi

    if [ "$ping_ok" = "true" ]; then
      internet_ok="true"
    else
      # Optional HTTP probe to avoid false negatives when ICMP is blocked.
      if command -v wget >/dev/null 2>&1; then
        if wget -T 2 -q -O /dev/null "$http_url" >/dev/null 2>&1; then
          http_ok="true"
          internet_ok="true"
          internet_reason="icmp blocked? http ok"
        else
          http_ok="false"
        fi
      elif command -v curl >/dev/null 2>&1; then
        if curl -m 2 -fsS -o /dev/null "$http_url" >/dev/null 2>&1; then
          http_ok="true"
          internet_ok="true"
          internet_reason="icmp blocked? http ok"
        else
          http_ok="false"
        fi
      fi

      if [ "$internet_ok" != "true" ]; then
        internet_ok="false"
        if [ "$gateway_ok" = "false" ]; then
          internet_reason="gateway unreachable"
        else
          internet_reason="ping failed"
        fi
      fi
    fi
  else
    internet_reason="ping not available"
  fi
else
  internet_reason="hotspot not running"
fi

http_json
printf '{ "ok": true, "status": {'
printf '"running":%s,' "$running"
printf '"iface":"%s",' "$(json_escape "$IFACE")"
printf '"state":"%s",' "$(json_escape "$state")"
printf '"activeConnection":"%s",' "$(json_escape "$active")"
printf '"ip":"%s",' "$(json_escape "${ip:-}")"
printf '"uplinkIface":"%s",' "$(json_escape "${uplink_iface:-}")"
printf '"routeDev":"%s",' "$(json_escape "${route_dev:-}")"
printf '"routeSrc":"%s",' "$(json_escape "${route_src:-}")"
printf '"gateway":"%s",' "$(json_escape "${gateway:-}")"
printf '"gatewayOk":%s,' "$gateway_ok"
printf '"ipForward":%s,' "$ip_forward_bool"
printf '"internetOk":%s,' "$internet_ok"
printf '"internetTarget":"%s"' "$(json_escape "$internet_target")"
if [ -n "${internet_reason:-}" ]; then
  printf ', "internetReason":"%s"' "$(json_escape "$internet_reason")"
fi
printf ', "httpOk":%s' "$http_ok"
printf '} }\n'
