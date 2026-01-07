#!/bin/sh
set -eu

export PATH="/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

DATA_DIR="${DATA_DIR:-/var/apps/fn-wifi-hotspot/target/server}"
CFG_FILE="${CFG_FILE:-$DATA_DIR/hotspot.env}"
NAT_STATE_FILE="${NAT_STATE_FILE:-$DATA_DIR/nat.env}"
PORTS_STATE_FILE="${PORTS_STATE_FILE:-$DATA_DIR/ports.state}"

# 默认配置
DEFAULT_CONNECTION_NAME="fn-hotspot"
DEFAULT_IFACE=""
DEFAULT_UPLINK_IFACE=""
DEFAULT_IP_CIDR=""
DEFAULT_ALLOW_PORTS=""
DEFAULT_SSID="fn-hotspot"
DEFAULT_PASSWORD="12345678"
DEFAULT_BAND="bg" # bg=2.4G, a=5G
DEFAULT_CHANNEL="6"

mkdir -p "$DATA_DIR" 2>/dev/null || true

trim_ws() {
  printf '%s' "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

allow_ports_to_rules() {
  # Input: "53,67-68,153/udp,167-168/udp" (spaces allowed)
  # Output: lines "proto\tstart\tend"; returns non-zero on invalid.
  spec="$(trim_ws "${1:-}")"
  [ -n "$spec" ] || return 0

  oldIFS=$IFS
  IFS=','
  # shellcheck disable=SC2086
  set -- $spec
  IFS=$oldIFS

  for tok in "$@"; do
    t="$(trim_ws "$tok")"
    [ -n "$t" ] || continue

    proto="tcp"
    portpart="$t"
    case "$t" in
      */*)
        proto="$(printf '%s' "${t##*/}" | tr 'A-Z' 'a-z')"
        portpart="${t%/*}"
        ;;
    esac

    proto="$(trim_ws "$proto")"
    portpart="$(trim_ws "$portpart")"

    [ "$proto" = "tcp" ] || [ "$proto" = "udp" ] || return 1
    [ -n "$portpart" ] || return 1

    start=""
    end=""
    case "$portpart" in
      *-*)
        start="$(trim_ws "${portpart%-*}")"
        end="$(trim_ws "${portpart#*-}")"
        ;;
      *)
        start="$portpart"
        end="$portpart"
        ;;
    esac

    case "$start" in '' | *[!0-9]*) return 1 ;; esac
    case "$end" in '' | *[!0-9]*) return 1 ;; esac

    [ "$start" -ge 1 ] 2>/dev/null || return 1
    [ "$end" -ge 1 ] 2>/dev/null || return 1
    [ "$start" -le 65535 ] 2>/dev/null || return 1
    [ "$end" -le 65535 ] 2>/dev/null || return 1
    [ "$start" -le "$end" ] 2>/dev/null || return 1

    printf '%s\t%s\t%s\n' "$proto" "$start" "$end"
  done
}

validate_allow_ports() {
  allow_ports_to_rules "${1:-}" >/dev/null 2>&1
}

write_ports_state() {
  iface="$1"
  rules="$2"
  umask 077
  if [ -n "${rules:-}" ]; then
    {
      printf 'iface\t%s\n' "$iface"
      printf '%s' "$rules"
    } >"$PORTS_STATE_FILE"
  else
    rm -f "$PORTS_STATE_FILE" 2>/dev/null || true
  fi
}

load_ports_state() {
  ps_iface=""
  ps_rules=""
  [ -r "$PORTS_STATE_FILE" ] || return 0
  ps_iface="$(head -n1 "$PORTS_STATE_FILE" 2>/dev/null | awk -F'\t' '$1=="iface"{print $2}' || true)"
  ps_rules="$(tail -n +2 "$PORTS_STATE_FILE" 2>/dev/null || true)"
}

iptables_allow_port() {
  iface="$1"
  proto="$2"
  start="$3"
  end="$4"
  [ -n "$iface" ] || return 0
  [ -n "$proto" ] || return 0
  [ -n "$start" ] || return 0
  [ -n "$end" ] || return 0
  command -v iptables >/dev/null 2>&1 || return 0

  dport="$start"
  if [ "$start" != "$end" ]; then
    dport="$start:$end"
  fi

  iptables -C INPUT -i "$iface" -p "$proto" --dport "$dport" -m comment --comment "fn-hotspot-allow" -j ACCEPT >/dev/null 2>&1 \
    || iptables -A INPUT -i "$iface" -p "$proto" --dport "$dport" -m comment --comment "fn-hotspot-allow" -j ACCEPT >/dev/null 2>&1 \
    || true
}

iptables_remove_port() {
  iface="$1"
  proto="$2"
  start="$3"
  end="$4"
  [ -n "$iface" ] || return 0
  command -v iptables >/dev/null 2>&1 || return 0

  dport="$start"
  if [ "$start" != "$end" ]; then
    dport="$start:$end"
  fi

  iptables -D INPUT -i "$iface" -p "$proto" --dport "$dport" -m comment --comment "fn-hotspot-allow" -j ACCEPT >/dev/null 2>&1 || true
}

apply_allow_ports() {
  hotspot_iface="$1"
  spec="$2"
  [ -n "${hotspot_iface:-}" ] || return 0

  # Clean previous rules first (in case iface/spec changed).
  remove_allow_ports

  rules_out=""
  if [ -n "${spec:-}" ]; then
    rules_out="$(allow_ports_to_rules "$spec" 2>/dev/null || true)"
  fi

  if [ -z "${rules_out:-}" ]; then
    write_ports_state "$hotspot_iface" ""
    return 0
  fi

  TAB="$(printf '\t')"
  applied=""
  while IFS="$TAB" read -r proto start end; do
    [ -n "${proto:-}" ] || continue
    iptables_allow_port "$hotspot_iface" "$proto" "$start" "$end"
    applied="$applied$proto$TAB$start$TAB$end\n"
  done <<EOF
$rules_out
EOF

  write_ports_state "$hotspot_iface" "$(printf '%b' "$applied")"
}

remove_allow_ports() {
  load_ports_state
  [ -n "${ps_iface:-}" ] || {
    rm -f "$PORTS_STATE_FILE" 2>/dev/null || true
    return 0
  }
  [ -n "${ps_rules:-}" ] || {
    rm -f "$PORTS_STATE_FILE" 2>/dev/null || true
    return 0
  }

  TAB="$(printf '\t')"
  while IFS="$TAB" read -r proto start end; do
    [ -n "${proto:-}" ] || continue
    iptables_remove_port "$ps_iface" "$proto" "$start" "$end"
  done <<EOF
$ps_rules
EOF

  rm -f "$PORTS_STATE_FILE" 2>/dev/null || true
}

detect_route_dev() {
  # Best-effort: find the interface used to reach a public IP.
  target="${1:-1.1.1.1}"
  if command -v ip >/dev/null 2>&1; then
    ip -4 route get "$target" 2>/dev/null | awk '{for(i=1;i<=NF;i++){if($i=="dev"){print $(i+1); exit}}}' || true
  fi
}

ensure_ip_forward() {
  command -v sysctl >/dev/null 2>&1 || return 0
  sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true
}

write_nat_state() {
  umask 077
  cat >"$NAT_STATE_FILE" <<EOF
HOTSPOT_IFACE=$(printf '%s' "$1")
NAT_UPLINK_IFACE=$(printf '%s' "$2")
EOF
}

clear_nat_state() {
  rm -f "$NAT_STATE_FILE" 2>/dev/null || true
}

load_nat_state() {
  HOTSPOT_IFACE=""
  NAT_UPLINK_IFACE=""
  if [ -f "$NAT_STATE_FILE" ]; then
    # shellcheck disable=SC1090
    . "$NAT_STATE_FILE" || true
  fi
}

iptables_apply_nat() {
  hotspot="$1"
  uplink="$2"
  [ -n "$hotspot" ] || return 0
  [ -n "$uplink" ] || return 0
  command -v iptables >/dev/null 2>&1 || return 0

  # NAT masquerade
  iptables -t nat -C POSTROUTING -o "$uplink" -j MASQUERADE >/dev/null 2>&1 \
    || iptables -t nat -A POSTROUTING -o "$uplink" -j MASQUERADE >/dev/null 2>&1 \
    || true

  # Allow forwarding between hotspot and uplink
  iptables -C FORWARD -i "$hotspot" -o "$uplink" -j ACCEPT >/dev/null 2>&1 \
    || iptables -A FORWARD -i "$hotspot" -o "$uplink" -j ACCEPT >/dev/null 2>&1 \
    || true
  iptables -C FORWARD -i "$uplink" -o "$hotspot" -j ACCEPT >/dev/null 2>&1 \
    || iptables -A FORWARD -i "$uplink" -o "$hotspot" -j ACCEPT >/dev/null 2>&1 \
    || true
}

iptables_remove_nat() {
  hotspot="$1"
  uplink="$2"
  [ -n "$hotspot" ] || return 0
  [ -n "$uplink" ] || return 0
  command -v iptables >/dev/null 2>&1 || return 0

  iptables -t nat -D POSTROUTING -o "$uplink" -j MASQUERADE >/dev/null 2>&1 || true
  iptables -D FORWARD -i "$hotspot" -o "$uplink" -j ACCEPT >/dev/null 2>&1 || true
  iptables -D FORWARD -i "$uplink" -o "$hotspot" -j ACCEPT >/dev/null 2>&1 || true
}

apply_hotspot_nat() {
  hotspot="$1"
  uplink="$2"
  [ -n "$hotspot" ] || return 0

  # Prefer caller-provided uplink; else follow actual route.
  if [ -z "${uplink:-}" ]; then
    uplink="$(detect_route_dev 1.1.1.1)"
  fi

  # If uplink is still empty, do nothing.
  [ -n "${uplink:-}" ] || return 0

  ensure_ip_forward
  iptables_apply_nat "$hotspot" "$uplink"
  write_nat_state "$hotspot" "$uplink"
}

remove_hotspot_nat() {
  load_nat_state
  if [ -n "${HOTSPOT_IFACE:-}" ] && [ -n "${NAT_UPLINK_IFACE:-}" ]; then
    iptables_remove_nat "$HOTSPOT_IFACE" "$NAT_UPLINK_IFACE"
  fi
  clear_nat_state
}

# 输出 JSON（最小转义）
json_escape() {
  # 仅处理 \ 和 " 和换行，足够用于本项目
  printf '%s' "$1" | sed \
    -e 's/\\/\\\\/g' \
    -e 's/"/\\"/g' \
    -e ':a;N;$!ba;s/\n/\\n/g'
}

http_json() {
  printf 'Content-Type: application/json\r\n'
  printf 'Cache-Control: no-store\r\n'
  printf '\r\n'
}

http_err() {
  code="$1"
  msg="$2"
  printf 'Status: %s\r\n' "$code"
  http_json
  printf '{ "ok": false, "error": "%s" }\n' "$(json_escape "$msg")"
  exit 0
}

wifi_ifaces() {
  if command -v nmcli >/dev/null 2>&1; then
    # TYPE 在不同环境可能是 wifi / wifi-p2p / 802-11-wireless 等
    nmcli -t -f DEVICE,TYPE dev status 2>/dev/null | awk -F: '($2 ~ /^wifi/) || ($2 ~ /wireless/){print $1}'
    return 0
  fi

  # Fallback: parse from `iw dev` output
  if command -v iw >/dev/null 2>&1; then
    iw dev 2>/dev/null | sed -n 's/^\s*Interface \(.*\)$/\1/p'
    return 0
  fi

  return 0
}

is_iface_name() {
  # Linux interface name (best-effort). Allow '', handled by caller.
  n="$1"
  printf '%s' "$n" | grep -Eq '^[a-zA-Z0-9_.:-]{1,64}$'
}

is_ipv4_cidr() {
  cidr="$1"
  printf '%s' "$cidr" | awk -F'/' '
    NF==2 {
      ip=$1; p=$2;
      if (p !~ /^[0-9]+$/) exit 1;
      if (p < 0 || p > 32) exit 1;
      n=split(ip, a, ".");
      if (n != 4) exit 1;
      for (i=1; i<=4; i++) {
        if (a[i] !~ /^[0-9]+$/) exit 1;
        if (a[i] < 0 || a[i] > 255) exit 1;
      }
      exit 0
    }
    { exit 1 }
  '
}

iface_is_wifi() {
  dev="$1"
  [ -n "$dev" ] || return 1
  command -v nmcli >/dev/null 2>&1 || return 0
  nmcli -t -f DEVICE,TYPE dev status 2>/dev/null | awk -F: -v d="$dev" '$1==d && (($2 ~ /^wifi/) || ($2 ~ /wireless/)) {ok=1} END{exit ok?0:1}'
}

ensure_iface() {
  # If IFACE is empty, try auto-pick a Wi-Fi device.
  if [ -z "${IFACE:-}" ]; then
    # Prefer a non-P2P device if available (e.g. avoid p2p-dev-wlan0).
    IFACE="$(wifi_ifaces | awk '!/^p2p/ {print; exit}' 2>/dev/null || true)"
    if [ -z "${IFACE:-}" ]; then
      IFACE="$(wifi_ifaces | head -n1 2>/dev/null || true)"
    fi
  fi
}

require_wifi_iface() {
  ensure_iface
  [ -n "${IFACE:-}" ] || return 2
  iface_is_wifi "$IFACE" || return 1
  return 0
}

load_cfg() {
  CONNECTION_NAME="$DEFAULT_CONNECTION_NAME"
  IFACE="$DEFAULT_IFACE"
  UPLINK_IFACE="$DEFAULT_UPLINK_IFACE"
  IP_CIDR="$DEFAULT_IP_CIDR"
  ALLOW_PORTS="$DEFAULT_ALLOW_PORTS"
  SSID="$DEFAULT_SSID"
  PASSWORD="$DEFAULT_PASSWORD"
  BAND="$DEFAULT_BAND"
  CHANNEL="$DEFAULT_CHANNEL"

  if [ -f "$CFG_FILE" ]; then
    # shellcheck disable=SC1090
    . "$CFG_FILE" || true
  fi

  : "${CONNECTION_NAME:=$DEFAULT_CONNECTION_NAME}"
  : "${IFACE:=$DEFAULT_IFACE}"
  : "${UPLINK_IFACE:=$DEFAULT_UPLINK_IFACE}"
  : "${IP_CIDR:=$DEFAULT_IP_CIDR}"
  : "${ALLOW_PORTS:=$DEFAULT_ALLOW_PORTS}"
  : "${SSID:=$DEFAULT_SSID}"
  : "${PASSWORD:=$DEFAULT_PASSWORD}"
  : "${BAND:=$DEFAULT_BAND}"
  : "${CHANNEL:=$DEFAULT_CHANNEL}"
}

save_cfg() {
  umask 077
  if cat >"$CFG_FILE" <<EOF; then
CONNECTION_NAME=$(printf '%s' "$CONNECTION_NAME")
IFACE=$(printf '%s' "$IFACE")
UPLINK_IFACE=$(printf '%s' "$UPLINK_IFACE")
IP_CIDR=$(printf '%s' "$IP_CIDR")
ALLOW_PORTS=$(printf '%s' "$ALLOW_PORTS")
SSID=$(printf '%s' "$SSID")
PASSWORD=$(printf '%s' "$PASSWORD")
BAND=$(printf '%s' "$BAND")
CHANNEL=$(printf '%s' "$CHANNEL")
EOF
    return 0
  fi
  return 1
}

# 读 POST body（支持 application/x-www-form-urlencoded）
read_body() {
  len="${CONTENT_LENGTH:-0}"
  if [ "$len" -gt 0 ] 2>/dev/null; then
    dd bs=1 count="$len" 2>/dev/null
  else
    cat
  fi
}

url_decode() {
  # + => space, %XX 解码（POSIX /bin/sh 兼容；不依赖 printf %b / \\x 支持）
  s="$1"
  out=""
  while [ -n "$s" ]; do
    c="${s%"${s#?}"}"
    s="${s#?}"

    if [ "$c" = "+" ]; then
      out="$out "
      continue
    fi

    if [ "$c" = "%" ]; then
      h1="${s%"${s#?}"}"
      s="${s#?}"
      h2="${s%"${s#?}"}"
      s="${s#?}"
      valid=1
      v1=0
      v2=0

      case "$h1" in
        0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9) v1=$h1 ;;
        a | A) v1=10 ;;
        b | B) v1=11 ;;
        c | C) v1=12 ;;
        d | D) v1=13 ;;
        e | E) v1=14 ;;
        f | F) v1=15 ;;
        *) valid=0 ;;
      esac

      case "$h2" in
        0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9) v2=$h2 ;;
        a | A) v2=10 ;;
        b | B) v2=11 ;;
        c | C) v2=12 ;;
        d | D) v2=13 ;;
        e | E) v2=14 ;;
        f | F) v2=15 ;;
        *) valid=0 ;;
      esac

      if [ "$valid" -eq 1 ]; then
        dec=$((v1 * 16 + v2))
        out="$out$(printf "\\$(printf '%03o' "$dec")")"
      else
        # malformed percent-escape: keep literal
        out="$out%$h1$h2"
      fi
      continue
    fi

    out="$out$c"
  done

  printf '%s' "$out"
}

# 从 form-urlencoded body 中取字段
form_get() {
  key="$1"
  body="$2"
  # shellcheck disable=SC2001
  val="$(printf '%s' "$body" | tr '&' '\n' | sed -n "s/^${key}=//p" | head -n1)"
  url_decode "${val:-}"
}

validate_cfg() {
  [ -n "$CONNECTION_NAME" ] || return 1
  # IFACE 可以留空（运行时自动选择 Wi-Fi 网卡）
  if [ -n "${UPLINK_IFACE:-}" ] && ! is_iface_name "$UPLINK_IFACE"; then return 1; fi
  if [ -n "${IP_CIDR:-}" ] && ! is_ipv4_cidr "$IP_CIDR"; then return 1; fi
  if [ -n "${ALLOW_PORTS:-}" ] && ! validate_allow_ports "$ALLOW_PORTS"; then return 1; fi
  [ -n "$SSID" ] || return 1
  [ "${#PASSWORD}" -ge 8 ] || return 1
  [ "$BAND" = "bg" ] || [ "$BAND" = "a" ] || return 1
  case "$CHANNEL" in
    *[!0-9]* | "") return 1 ;;
  esac
  return 0
}
