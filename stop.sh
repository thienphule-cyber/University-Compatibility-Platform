#!/usr/bin/env bash
# stop.sh - stop the UCRP server started by start.sh.
set -uo pipefail

cd "$(dirname "$0")"

PID_FILE=".ucrp.pid"
PORT_FILE=".ucrp.port"

if [ ! -f "$PID_FILE" ]; then
  echo "UCRP is not running (no PID file)."
  rm -f "$PORT_FILE"
  exit 0
fi

PID="$(cat "$PID_FILE")"

if ! kill -0 "$PID" 2>/dev/null; then
  echo "UCRP is not running (stale PID file removed)."
  rm -f "$PID_FILE" "$PORT_FILE"
  exit 0
fi

# Safety check: only kill the process if it is really our uvicorn server
if ! ps -p "$PID" -o command= | grep -q "backend.main:app"; then
  echo "PID $PID is not a UCRP server. Removing stale files without killing it."
  rm -f "$PID_FILE" "$PORT_FILE"
  exit 0
fi

kill "$PID" 2>/dev/null
for _ in $(seq 1 20); do          # wait up to ~5 seconds for a clean shutdown
  kill -0 "$PID" 2>/dev/null || break
  sleep 0.25
done

if kill -0 "$PID" 2>/dev/null; then
  kill -9 "$PID" 2>/dev/null
fi

rm -f "$PID_FILE" "$PORT_FILE"
echo "UCRP stopped."