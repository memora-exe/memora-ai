#!/usr/bin/env bash
set -e

PORT="${GRPC_PORT:-50051}"
export PYTHONPATH=".:./proto:./app/interfaces/grpc:$PYTHONPATH"

echo ">>> Starting Stateless AI gRPC Server on port $PORT..."
if [ -f "venv/bin/python" ]; then
    PYTHON_CMD="venv/bin/python"
elif [ -f "venv/Scripts/python.exe" ]; then
    PYTHON_CMD="venv/Scripts/python.exe"
else
    PYTHON_CMD="python"
fi

exec $PYTHON_CMD -m app.interfaces.grpc.server
