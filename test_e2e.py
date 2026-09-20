#!/usr/bin/env python3
"""E2E test: Login via BE, then call stream chat through the same path the FE uses.

Usage: python test_e2e.py
"""
import json
import sys
import time

# Force UTF-8 stdout on Windows so we can print Vietnamese characters
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import requests

BE = "http://localhost:3000"
AI = "http://localhost:3100"
EMAIL = "admin@example.com"
PASSWORD = "Admin@123"
PROJECT_ID = "2e3ff753-3622-48fc-a6b7-0a14b93ab68e"

# ----- Step 1: Login ----------------------------------------------------
print("=" * 60)
print("STEP 1: Login to BE")
print("=" * 60)
try:
    r = requests.post(
        f"{BE}/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=10,
    )
    print(f"Status: {r.status_code}")
    print(f"Body: {r.text[:500]}")
    if r.status_code not in (200, 201):
        print("LOGIN FAILED — cannot continue")
        sys.exit(1)
    tokens = r.json()
    access_token = tokens["accessToken"]
    print(f"Got accessToken: {access_token[:40]}...")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    sys.exit(1)

headers = {"Authorization": f"Bearer {access_token}"}

# ----- Step 2: List sessions (use the same project) --------------------
print()
print("=" * 60)
print("STEP 2: List AI sessions for project")
print("=" * 60)
try:
    r = requests.get(
        f"{BE}/projects/{PROJECT_ID}/ai/sessions",
        headers=headers,
        timeout=10,
    )
    print(f"Status: {r.status_code}")
    print(f"Body: {r.text[:1500]}")
    if r.status_code in (200, 201):
        sessions = r.json()
        if isinstance(sessions, list) and len(sessions) > 0:
            session_id = sessions[0]["id"]
        else:
            session_id = None
    else:
        session_id = None
    if not session_id:
        # Create a new session
        print("Creating a new session...")
        r = requests.post(
            f"{BE}/projects/{PROJECT_ID}/ai/sessions",
            headers=headers,
            json={},
            timeout=10,
        )
        print(f"Create status: {r.status_code}, body: {r.text[:500]}")
        session_id = r.json()["id"]
    print(f"Using session_id: {session_id}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    sys.exit(1)

# ----- Step 3: Stream chat via BE (the FE path) -------------------------
print()
print("=" * 60)
print("STEP 3: Stream chat through BE (exactly like FE does)")
print("=" * 60)
try:
    r = requests.post(
        f"{BE}/projects/{PROJECT_ID}/ai/sessions/{session_id}/stream",
        headers=headers,
        json={"message": "chào bạn"},
        stream=True,
        timeout=120,
    )
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('Content-Type')}")
    print("SSE stream:")
    accumulated = ""
    line_count = 0
    for line in r.iter_lines(decode_unicode=True):
        if line is None:
            continue
        line_count += 1
        print(f"  [{line_count}] {line[:300]}")
        if line.startswith("data:"):
            try:
                payload = json.loads(line[5:].strip())
                if isinstance(payload, dict) and "chunk" in payload:
                    accumulated += payload["chunk"]
            except json.JSONDecodeError:
                pass
    print(f"--- accumulated text: {accumulated!r}")
    if not accumulated:
        print("\n!!! EMPTY RESPONSE FROM AI !!!")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

# ----- Step 4: Direct AI service test (bypass BE) -----------------------
print()
print("=" * 60)
print("STEP 4: Direct call to AI service /api/chat/stream")
print("=" * 60)
try:
    r = requests.post(
        f"{AI}/api/chat/stream",
        json={
            "message": "chào bạn",
            "session_id": session_id,
            "project_id": PROJECT_ID,
            "jwt_token": access_token,
        },
        stream=True,
        timeout=120,
    )
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('Content-Type')}")
    accumulated = ""
    line_count = 0
    for line in r.iter_lines(decode_unicode=True):
        if line is None:
            continue
        line_count += 1
        print(f"  [{line_count}] {line[:300]}")
        if line.startswith("data:"):
            try:
                payload = json.loads(line[5:].strip())
                if isinstance(payload, dict) and "chunk" in payload:
                    accumulated += payload["chunk"]
            except json.JSONDecodeError:
                pass
    print(f"--- accumulated text: {accumulated!r}")
    if not accumulated:
        print("\n!!! AI SERVICE DIRECTLY RETURNED EMPTY !!!")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

# ----- Step 5: Import and run in-process to capture the exact traceback -
print()
print("=" * 60)
print("STEP 5: Import and run in-process to capture exact traceback")
print("=" * 60)
try:
    import os
    import django # just checking environment, not needed
except ImportError:
    pass

try:
    # Add project root to sys.path
    import os
    import sys
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

    from app.services.chat.chat_service import process_chat_message_stream
    import asyncio

    async def run_in_process():
        print("Starting in-process stream...")
        try:
            async for chunk in process_chat_message_stream(
                message="chào bạn",
                session_id=session_id,
                project_id=PROJECT_ID,
                jwt_token=access_token,
            ):
                print(f"  Got chunk: {chunk}")
            print("Stream completed successfully!")
        except Exception as e:
            print("CRITICAL ERROR IN-PROCESS:")
            import traceback
            traceback.print_exc()

    asyncio.run(run_in_process())
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

sys.stdout.flush()
