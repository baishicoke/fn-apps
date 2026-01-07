#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"

load_cfg
ensure_iface

TAB="$(printf '\t')"

stations=""
if command -v iw >/dev/null 2>&1; then
  stations="$(iw dev "$IFACE" station dump 2>/dev/null | awk '
    BEGIN{mac=""; sig=""; ct=""; rx=""; tx=""}
    /^Station /{
      if (mac!="") {print mac"\t"sig"\t"ct"\t"rx"\t"tx}
      mac=$2; sig=""; ct=""; rx=""; tx="";
      next
    }
    $1=="signal:"{sig=$2; next}
    $1=="connected" && $2=="time:"{ct=$3; next}
    $1=="rx" && $2=="bytes:"{rx=$3; next}
    $1=="tx" && $2=="bytes:"{tx=$3; next}
    END{ if (mac!="") {print mac"\t"sig"\t"ct"\t"rx"\t"tx} }
  ' || true)"
fi

# Neighbor table: MAC -> IP (best-effort)
neigh=""
if command -v ip >/dev/null 2>&1; then
  neigh="$(ip neigh show dev "$IFACE" 2>/dev/null | awk '{for(i=1;i<=NF;i++){if($i=="lladdr"){print $(i+1)"\t"$1}}}' || true)"
fi

# Best-effort hostname mapping from DHCP leases (MAC/IP -> hostname)
lease_hosts_mac=""
lease_hosts_ip=""
if command -v awk >/dev/null 2>&1; then
  leases_raw=""
  for f in /var/lib/NetworkManager/dnsmasq-*.leases /var/lib/misc/dnsmasq.leases /tmp/dnsmasq.leases; do
    [ -r "$f" ] || continue
    leases_raw="$leases_raw$(cat "$f" 2>/dev/null || true)
"
  done

  if [ -n "${leases_raw:-}" ]; then
    lease_hosts_mac="$(printf '%s' "$leases_raw" | awk '
      NF>=4 {
        mac=$2; ip=$3; host=$4;
        if (host=="" || host=="*" || host=="-") next;
        # normalize mac
        gsub(/[A-F]/, "", mac);
      }
    ' 2>/dev/null)"
    # The above awk block was intentionally left minimal; do actual parsing below.
    lease_hosts_mac="$(printf '%s' "$leases_raw" | awk '
      NF>=4 {
        mac=tolower($2); ip=$3; host=$4;
        if (host=="" || host=="*" || host=="-") next;
        print mac"\t"host;
      }
    ' 2>/dev/null || true)"
    lease_hosts_ip="$(printf '%s' "$leases_raw" | awk '
      NF>=4 {
        ip=$3; host=$4;
        if (host=="" || host=="*" || host=="-") next;
        print ip"\t"host;
      }
    ' 2>/dev/null || true)"
  fi
fi

http_json
printf '{ "ok": true, "clients": ['
first=1
seen=" "

emit_client() {
  mac="$1"
  ipaddr="$2"
  sig="$3"
  ct="$4"
  rx_bytes="$5"
  tx_bytes="$6"
  [ -n "$mac" ] || return 0

  case "$seen" in
    *" $mac "*) return 0 ;;
  esac
  seen="$seen$mac "

  if [ $first -eq 1 ]; then first=0; else printf ','; fi

  printf '{ "mac":"%s"' "$(json_escape "$mac")"
  hostname=""
  if [ -n "${lease_hosts_mac:-}" ]; then
    hostname="$(printf '%s\n' "$lease_hosts_mac" | awk -v m="$mac" 'tolower($1)==tolower(m){print $2; exit}' || true)"
  fi
  if [ -z "${hostname:-}" ] && [ -n "${ipaddr:-}" ] && [ -n "${lease_hosts_ip:-}" ]; then
    hostname="$(printf '%s\n' "$lease_hosts_ip" | awk -v ip="$ipaddr" '$1==ip{print $2; exit}' || true)"
  fi
  if [ -z "${hostname:-}" ] && [ -n "${ipaddr:-}" ] && command -v getent >/dev/null 2>&1; then
    hostname="$(getent hosts "$ipaddr" 2>/dev/null | awk '{print $2; exit}' || true)"
  fi
  if [ -n "${hostname:-}" ]; then
    printf ', "hostname":"%s"' "$(json_escape "$hostname")"
  fi
  if [ -n "${ipaddr:-}" ]; then
    printf ', "ip":"%s"' "$(json_escape "$ipaddr")"
  fi
  if [ -n "${sig:-}" ]; then
    printf ', "signalDbm":%s' "$(json_escape "$sig")"
  fi
  if [ -n "${ct:-}" ]; then
    printf ', "connectedSeconds":%s' "$(json_escape "$ct")"
  fi
  if [ -n "${rx_bytes:-}" ]; then
    printf ', "rxBytes":%s' "$(json_escape "$rx_bytes")"
  fi
  if [ -n "${tx_bytes:-}" ]; then
    printf ', "txBytes":%s' "$(json_escape "$tx_bytes")"
  fi
  printf ' }'
}

# Prefer station dump first (includes signal/time). Add IP if present in neigh.
if [ -n "${stations:-}" ]; then
  while IFS="$TAB" read -r mac sig ct rx tx; do
    [ -n "${mac:-}" ] || continue
    ipaddr="$(printf '%s\n' "$neigh" | awk -v m="$mac" '$1==m{print $2; exit}')"
    emit_client "$mac" "$ipaddr" "$sig" "$ct" "$rx" "$tx"
  done <<EOF
$stations
EOF
fi

# Then add neighbor-derived entries not in station list.
# Only use neighbor table as fallback when we have no station data.
# Neighbor entries can linger after a client disconnects (STALE), causing ghost clients.
if [ -z "${stations:-}" ] && [ -n "${neigh:-}" ]; then
  while IFS="$TAB" read -r mac ipaddr; do
    [ -n "${mac:-}" ] || continue
    emit_client "$mac" "$ipaddr" "" "" "" ""
  done <<EOF
$neigh
EOF
fi
printf '] }\n'
