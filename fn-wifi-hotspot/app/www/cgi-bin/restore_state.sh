#!/bin/sh
# Restore hotspot enable state (intended to be run at boot)
set -eu
. "$(dirname "$0")/common.sh"

if [ $# -eq 0 ]; then
  echo "Usage: $0 {start|stop}"
  exit 1
fi

load_hotspot_state
if [ "${HOTSPOT_ENABLED:-0}" = "1" ]; then
  cd "$(dirname "$0")" || exit 1

  case $1 in
    start)
      # Try to start hotspot up to N times; check hotspot.state for success.
      for _ in $(seq 1 5); do
        env QUERY_STRING='' REQUEST_METHOD=GET ./start.cgi | grep -q '"ok": true' && break
        sleep 5
      done
      ;;
    stop)
      # Try to stop hotspot (best-effort)
      for _ in $(seq 1 5); do
        env QUERY_STRING='' REQUEST_METHOD=GET ./stop.cgi | grep -q '"ok": true' && break
        sleep 5
      done
      ;;
  esac
fi
