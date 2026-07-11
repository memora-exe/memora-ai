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

# 1. Kill any existing uvicorn process on port 8000
print("Killing existing uvicorn (port 8000)...")
try:
    # Use netstat to find PID
    r = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True, text=True, timeout=10
    )
    pids = set()
    for line in r.stdout.splitlines():
        if ":8000" in line and "LISTENING" in line:
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.add(parts[-1])
    for pid in pids:
        print(f"  Killing PID {pid}...")
        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
except FileNotFoundError:
    # Bash on Windows might not have netstat
    print("  netstat not found, trying tasklist...")

# Also kill any python.exe running app.main:app
print("Looking for python uvicorn processes...")
try:
    r = subprocess.run(
        ["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine"],
        capture_output=True, text=True, timeout=10
    )
    for line in r.stdout.splitlines():
        if "app.main" in line or "uvicorn" in line:
            # Extract PID
            parts = line.strip().split()
            if parts and parts[-1].isdigit():
                pid = parts[-1]
                print(f"  Killing PID {pid}: {line.strip()[:100]}")
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
except FileNotFoundError:
    pass

# 2. Start uvicorn in the background
print("Starting uvicorn (gemini-2.5-flash)...")
env = os.environ.copy()
env["GOOGLE_API_KEY"] = open(".env").read().split("GOOGLE_API_KEY=")[1].split("\n")[0].strip()

# Run in background — detached process
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
subprocess.Popen(
    ["./venv/Scripts/python.exe", "-m", "uvicorn", "app.main:app",
     "--host", "0.0.0.0", "--port", "8000", "--reload"],
    env=env,
    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
    close_fds=True,
)

time.sleep(3)
print("Waiting for service to be ready...")

# 3. Wait for health check
import requests
for i in range(30):
    try:
        r = requests.get("http://localhost:8000/health", timeout=2)
        if r.status_code == 200:
            print(f"Service ready! Health: {r.json()}")
            sys.exit(0)
    except Exception:
        pass
    time.sleep(1)
    print(f"  waiting... {i+1}s")

print("Service did not become ready in 30s")
sys.exit(1)
