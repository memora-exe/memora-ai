#!/usr/bin/env python3
"""E2E: upload gomaa PDF → poll until completed → chat → assert response."""
import json
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import requests

BE = "http://localhost:3000"
PDF = r"C:\Users\Admin\Downloads\gomaa-softwaremodellinganddesign.pdf"

# ----- Step 1: Login ----------------------------------------------------
print("=" * 60); print("STEP 1: Login"); print("=" * 60)
r = requests.post(f"{BE}/auth/login",
                  json={"email": "admin@example.com", "password": "Admin@123"},
                  timeout=10)
print(f"  status={r.status_code}")
if r.status_code not in (200, 201):
    print(f"  body={r.text[:300]}"); sys.exit(1)
access_token = r.json()["accessToken"]
headers = {"Authorization": f"Bearer {access_token}"}
print(f"  token={access_token[:30]}...")

# ----- Step 2: Pick or create project ----------------------------------
print(); print("=" * 60); print("STEP 2: Find/create project"); print("=" * 60)
r = requests.get(f"{BE}/projects", headers=headers, timeout=10)
projects = r.json() if r.status_code == 200 else []
if projects:
    PROJECT_ID = projects[0]["id"]
    print(f"  using existing project={PROJECT_ID}")
else:
    r = requests.post(f"{BE}/projects", headers=headers,
                      json={"projectName": "PDF Test", "isPublic": True},
                      timeout=10)
    print(f"  create status={r.status_code} body={r.text[:300]}")
    PROJECT_ID = r.json().get("projectId") or r.json().get("id")
    print(f"  created project={PROJECT_ID}")

# ----- Step 3: Upload PDF ---------------------------------------------
print(); print("=" * 60); print("STEP 3: Upload PDF"); print("=" * 60)
with open(PDF, "rb") as f:
    r = requests.post(
        f"{BE}/files/upload",
        headers=headers,
        data={"projectId": PROJECT_ID},
        files={"file": ("gomaa-softwaremodellinganddesign.pdf", f, "application/pdf")},
        timeout=60,
    )
print(f"  upload status={r.status_code}")
print(f"  body[:400]={r.text[:400]}")
if r.status_code not in (200, 201):
    print("  UPLOAD FAILED"); sys.exit(1)
file_id = r.json().get("id") or r.json().get("fileId")
print(f"  file_id={file_id}")

# ----- Step 4: Poll processingStatus until completed/failed -----------
print(); print("=" * 60); print("STEP 4: Poll status (≤ 10 min)"); print("=" * 60)
deadline = time.time() + 600
status = "unknown"
while time.time() < deadline:
    r = requests.get(f"{BE}/files/{file_id}", headers=headers, timeout=10)
    if r.status_code == 200:
        body = r.json()
        status = body.get("processingStatus") or body.get("processing_status") or "unknown"
        print(f"  t={int(time.time())%10000:5d}s status={status}")
        if status in ("completed", "failed"):
            break
    else:
        print(f"  poll status={r.status_code}")
    time.sleep(15)
print(f"  FINAL status={status}")

# ----- Step 5: List sessions ------------------------------------------
print(); print("=" * 60); print("STEP 5: Get/create AI session"); print("=" * 60)
r = requests.get(f"{BE}/projects/{PROJECT_ID}/ai/sessions", headers=headers, timeout=10)
sessions = r.json() if r.status_code == 200 else []
if isinstance(sessions, list) and sessions:
    session_id = sessions[0]["id"]
else:
    r = requests.post(f"{BE}/projects/{PROJECT_ID}/ai/sessions",
                      headers=headers, json={}, timeout=10)
    session_id = r.json()["id"]
print(f"  session_id={session_id}")

# ----- Step 6: Chat — summarize first page ----------------------------
print(); print("=" * 60); print("STEP 6: Chat 'summarize the first page'"); print("=" * 60)
t0 = time.perf_counter()
try:
    r = requests.post(
        f"{BE}/projects/{PROJECT_ID}/ai/sessions/{session_id}/stream",
        headers=headers,
        json={"message": "summarize the first page of the uploaded PDF"},
        stream=True,
        timeout=120,
    )
    print(f"  status={r.status_code} CT={r.headers.get('Content-Type')}")
    accumulated = ""
    citations = None
    for line in r.iter_lines(decode_unicode=True):
        if not line: continue
        if line.startswith("data:"):
            try:
                p = json.loads(line[5:].strip())
                if isinstance(p, dict):
                    if "chunk" in p: accumulated += p["chunk"]
                    if "metadata" in p: citations = p["metadata"]
            except Exception: pass
    dt = time.perf_counter() - t0
    print(f"  elapsed={dt:.1f}s len={len(accumulated)}")
    print(f"  text[:400]={accumulated[:400]!r}")
    print(f"  chunks_in_metadata={len((citations or {}).get('chunks', []))}")
except Exception as e:
    print(f"  ERROR: {type(e).__name__}: {e}")

# ----- Step 7: Chat — highlight all nodes -----------------------------
print(); print("=" * 60); print("STEP 7: Chat 'highlight all nodes'"); print("=" * 60)
t0 = time.perf_counter()
try:
    r = requests.post(
        f"{BE}/projects/{PROJECT_ID}/ai/sessions/{session_id}/stream",
        headers=headers,
        json={"message": "highlight tất cả các node trong project"},
        stream=True,
        timeout=120,
    )
    accumulated = ""
    citations = None
    for line in r.iter_lines(decode_unicode=True):
        if not line: continue
        if line.startswith("data:"):
            try:
                p = json.loads(line[5:].strip())
                if isinstance(p, dict):
                    if "chunk" in p: accumulated += p["chunk"]
                    if "metadata" in p: citations = p["metadata"]
                    if "error" in p: print(f"  ERROR_EVENT: {p['error']}")
            except Exception: pass
    dt = time.perf_counter() - t0
    print(f"  elapsed={dt:.1f}s len={len(accumulated)}")
    print(f"  text[:400]={accumulated[:400]!r}")
    print(f"  chunks={len((citations or {}).get('chunks', []))} nodes={len((citations or {}).get('citedNodes', []))}")
except Exception as e:
    print(f"  ERROR: {type(e).__name__}: {e}")

print(); print("DONE")