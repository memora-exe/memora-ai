#!/usr/bin/env python3
"""Test the AI chat endpoints exactly as the frontend/NestJS backend calls them.

Usage: python test_api.py
"""
import requests
import json
import sys
import time

import os
from dotenv import load_dotenv

load_dotenv()
PORT = os.getenv("PORT", "3020")
API = f"http://localhost:{PORT}"
SESSION_ID = "422cd396-f00d-417e-84d0-623832435df1"
PROJECT_ID = "2e3ff753-3622-48fc-a6b7-0a14b93ab68e"
JWT_TOKEN = "test-jwt-token"

# ----- Test 1: Health check -----------------------------------------
print("=" * 60)
print("TEST 1: Health check")
print("=" * 60)
try:
    r = requests.get(f"{API}/health", timeout=5)
    print(f"Status: {r.status_code}")
    print(f"Body: {r.text}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

# ----- Test 2: Standard (non-stream) chat ----------------------------
print()
print("=" * 60)
print("TEST 2: POST /api/chat/ (non-stream)")
print("=" * 60)
try:
    r = requests.post(
        f"{API}/api/chat/",
        json={
            "message": "chào bạn",
            "session_id": SESSION_ID,
            "project_id": PROJECT_ID,
            "jwt_token": JWT_TOKEN,
        },
        timeout=90,
    )
    print(f"Status: {r.status_code}")
    print(f"Body: {r.text[:1500]}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

# ----- Test 3: SSE stream (what FE actually uses) -------------------
print()
print("=" * 60)
print("TEST 3: POST /api/chat/stream (SSE)")
print("=" * 60)
try:
    r = requests.post(
        f"{API}/api/chat/stream",
        json={
            "message": "dsa",
            "session_id": SESSION_ID,
            "project_id": PROJECT_ID,
            "jwt_token": JWT_TOKEN,
        },
        stream=True,
        timeout=90,
    )
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('Content-Type')}")
    print("Streaming chunks:")
    accumulated = ""
    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue
        print(f"  {line}")
        if line.startswith("data:"):
            try:
                payload = json.loads(line[5:].strip())
                if isinstance(payload, dict) and "chunk" in payload:
                    accumulated += payload["chunk"]
            except json.JSONDecodeError:
                pass
    print(f"--- accumulated text: {accumulated!r}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

sys.stdout.flush()
