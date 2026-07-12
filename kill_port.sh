#!/usr/bin/env bash
# Kill any process listening on a port (default 3010).
# Usage: kill_port.sh [PORT]
set -e
PORT="${1:-3010}"

echo "Looking for PIDs on port $PORT..."
PIDS=$(netstat -ano | grep ":$PORT" | grep LISTENING | awk '{print $NF}' | sort -u)

if [ -z "$PIDS" ]; then
    echo "Port $PORT is free."
    exit 0
fi

for pid in $PIDS; do
    echo "Killing PID $pid..."
    taskkill //F //PID "$pid"
done
echo "Done."