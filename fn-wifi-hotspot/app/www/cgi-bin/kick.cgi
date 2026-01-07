#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"

STEP="init"
cleanup() {
  rc=$?
  if [ "$rc" -ne 0 ]; then
    trap - EXIT
    http_err "500 Internal Server Error" "kick.cgi failed (rc=$rc, step=$STEP)"
  fi
}
trap cleanup EXIT

load_cfg

# Parse mac from query string: kick.cgi?mac=xx:xx:xx:xx:xx:xx
qs="${QUERY_STRING:-}"
raw="$(printf '%s' "$qs" | tr '&' '\n' | sed -n 's/^mac=//p' | head -n1)"
STEP="decode"
MAC="$(url_decode "${raw:-}")"
MAC="$(printf '%s' "$MAC" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | tr 'A-F' 'a-f')"

if ! printf '%s' "$MAC" | grep -Eiq '^[0-9a-f]{2}(:[0-9a-f]{2}){5}$'; then
  http_err "400 Bad Request" "invalid mac: $MAC"
fi

STEP="iface"

if ! require_wifi_iface; then
  http_err "400 Bad Request" "no wifi iface"
fi

if ! command -v iw >/dev/null 2>&1; then
  http_err "500 Internal Server Error" "iw not found"
fi

out=""
STEP="kick"
if out="$(iw dev "$IFACE" station del "$MAC" 2>&1)"; then
  # Best-effort: remove neighbor cache for this MAC to avoid lingering entries.
  if command -v ip >/dev/null 2>&1; then
    ipaddr="$(ip neigh show dev "$IFACE" 2>/dev/null | awk -v m="$MAC" '{for(i=1;i<=NF;i++){if($i=="lladdr" && $(i+1)==m){print $1; exit}}}' || true)"
    if [ -n "${ipaddr:-}" ]; then
      ip neigh del "$ipaddr" dev "$IFACE" >/dev/null 2>&1 || true
    fi
  fi
  http_json
  printf '{ "ok": true, "output": "%s" }\n' "$(json_escape "$out")"
  trap - EXIT
  exit 0
fi

http_err "500 Internal Server Error" "kick failed: $out"
