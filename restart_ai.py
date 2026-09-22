#!/usr/bin/env python3
"""Kill any running uvicorn process and restart the AI service.

Usage: python restart_ai.py
"""
import os
import subprocess
import sys
import time

# Force UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Read port from .env
PORT = 3020
for line in open(".env").read().splitlines():
    if line.startswith("PORT="):
        PORT = int(line.split("PORT=")[1].strip())
        break

print(f"Target port: {PORT}")

# 1. Kill any existing uvicorn process on port PORT
print(f"Killing existing uvicorn (port {PORT})...")
try:
    r = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True, text=True, timeout=10
    )
    pids = set()
    for line in r.stdout.splitlines():
        if f":{PORT}" in line and "LISTENING" in line:
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.add(parts[-1])
    for pid in pids:
        print(f"  Killing PID {pid}...")
        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
except FileNotFoundError:
    print("  netstat not found, trying tasklist...")

# Also kill any python.exe running app.main:app
print("Looking for python uvicorn processes...")
try:
    my_pid = str(os.getpid())
    r = subprocess.run(
        ["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine"],
        capture_output=True, text=True, timeout=10
    )
    for line in r.stdout.splitlines():
        if ("app.main" in line or "uvicorn" in line) and my_pid not in line:
            parts = line.strip().split()
            if parts and parts[-1].isdigit():
                pid = parts[-1]
                print(f"  Killing uvicorn PID {pid}: {line.strip()[:100]}")
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
except FileNotFoundError:
    pass

# Wait for port to be completely free
print(f"Waiting for port {PORT} to be completely released...")
for _ in range(10):
    r = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True, text=True, timeout=10
    )
    port_in_use = False
    for line in r.stdout.splitlines():
        if f":{PORT}" in line and "LISTENING" in line:
            port_in_use = True
            break
    if not port_in_use:
        print(f"  Port {PORT} is now free!")
        break
    time.sleep(1)
else:
    print(f"  Warning: Port {PORT} is still in use after 10s, forcing start anyway...")

# 2. Start uvicorn in the background
print(f"Starting uvicorn (gemini-2.5-flash) on port {PORT}...")
env = os.environ.copy()
api_key = ""
for line in open(".env").read().splitlines():
    if line.startswith("GOOGLE_API_KEY="):
        api_key = line.split("GOOGLE_API_KEY=")[1].strip()
        break
env["GOOGLE_API_KEY"] = api_key
env["PYTHONUNBUFFERED"] = "1"
env["PYTHONPATH"] = "."

# Run in background — detached process and redirect output to uvicorn.log
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
log_file = open("uvicorn.log", "w", encoding="utf-8")
subprocess.Popen(
    ["./venv/Scripts/python.exe", "-m", "uvicorn", "app.main:app",
     "--host", "0.0.0.0", "--port", str(PORT)],
    env=env,
    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
    stdout=log_file,
    stderr=subprocess.STDOUT,
    close_fds=False, # Must be False to pass handles on Windows
)

time.sleep(3)
print("Waiting for service to be ready...")

# 3. Wait for health check
import requests
for i in range(30):
    try:
        r = requests.get(f"http://localhost:{PORT}/health", timeout=2)
        if r.status_code == 200:
            print(f"Service ready! Health: {r.json()}")
            sys.exit(0)
    except Exception:
        pass
    time.sleep(1)
    print(f"  waiting... {i+1}s")

print(f"Service did not become ready on port {PORT} in 30s")
sys.exit(1)
