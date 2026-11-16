#!/usr/bin/env bash
# start.sh - start UCRP in the background on a free port and open it in the browser.
set -euo pipefail

cd "$(dirname "$0")"

PID_FILE=".ucrp.pid"
PORT_FILE=".ucrp.port"
LOG_FILE="ucrp.log"
HOST="127.0.0.1"
PYTHON="venv/bin/python"

open_url() {
  if command -v open >/dev/null 2>&1; then
    open "$1"            # macOS
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$1"        # Linux
  fi
}

# Already running? Just reopen the existing link.
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  URL="http://$HOST:$(cat "$PORT_FILE")"
  echo "UCRP is already running: $URL"
  open_url "$URL"
  exit 0
fi

if [ ! -x "$PYTHON" ]; then
  echo "Virtual environment not found at ./venv. Create it first:"
  echo "  python3.12 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

# Find the first free port between 8000 and 8100
PORT="$("$PYTHON" - <<'EOF'
import socket
for p in range(8000, 8100):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p))
        print(p)
        break
    except OSError:
        pass
    finally:
        s.close()
else:
    raise SystemExit(1)
EOF
)" || { echo "No free port found between 8000 and 8100."; exit 1; }

# Start the server detached from the terminal (survives closing the terminal window)
nohup "$PYTHON" -m uvicorn backend.main:app --host "$HOST" --port "$PORT" >"$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"
echo "$PORT" > "$PORT_FILE"
disown "$SERVER_PID" 2>/dev/null || true

URL="http://$HOST:$PORT"
echo "Starting UCRP on $URL ..."

# Wait until the health endpoint responds (max ~30 seconds)
for _ in $(seq 1 60); do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "Server stopped unexpectedly. Last log lines:"
    tail -n 20 "$LOG_FILE"
    rm -f "$PID_FILE" "$PORT_FILE"
    exit 1
  fi
  if curl -fs "$URL/api/health" >/dev/null 2>&1; then
    echo "UCRP is ready: $URL"
    open_url "$URL"
    echo "Stop it with: ./stop.sh   (logs: $LOG_FILE)"
    exit 0
  fi
  sleep 0.5
done

echo "Server did not become ready in time. Check $LOG_FILE"
exit 1