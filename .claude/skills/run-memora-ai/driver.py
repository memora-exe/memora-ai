#!/usr/bin/env python3
"""smoke driver for memora-ai (FastAPI).
Stdlib only — no requests / httpx dep.

Usage:
  python driver.py health [baseUrl]                  # probe /health and /docs
  python driver.py paths [baseUrl]                   # dump /openapi.json paths
  python driver.py curl <METHOD> <path> [baseUrl]     # one-shot request

Examples:
  python driver.py health
  python driver.py paths
  python driver.py curl POST /api/chat/ -d '{"message":"hi"}'
"""
import json, sys, urllib.request, urllib.error
from urllib.parse import urljoin

def fetch(url, method="GET", data=None, headers=None):
    h = {"Content-Type": "application/json", **(headers or {})}
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        return 0, str(e.reason)

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__); return

    op, *rest = args
    base = next((a for a in rest if a.startswith("http")), "http://localhost:8000")
    base = base.rstrip("/") + "/"

    if op == "health":
        bad = 0
        for path in ("/health", "/docs", "/openapi.json"):
            code, body = fetch(urljoin(base, path))
            ok = code == 200
            print(f"{'OK ' if ok else 'BAD'}  {code}  {base}{path}  {body[:60]!r}")
            if not ok: bad += 1
        sys.exit(1 if bad else 0)

    if op == "paths":
        code, body = fetch(urljoin(base, "/openapi.json"))
        if code != 200:
            print(f"openapi.json returned {code}"); sys.exit(1)
        doc = json.loads(body)
        paths = list(doc.get("paths", {}).keys())
        print(f"{len(paths)} paths:")
        for p in paths: print("  " + p)
        return

    if op == "curl":
        if len(rest) < 2:
            print("curl needs <METHOD> <path>"); sys.exit(2)
        method, path = rest[0].upper(), rest[1]
        if not path.startswith("/"): path = "/" + path
        # data may be passed as `-d '{"..."}'`
        data = None
        if "-d" in rest:
            i = rest.index("-d")
            data = json.loads(rest[i + 1])
        code, body = fetch(urljoin(base, path), method=method, data=data)
        print(f"status: {code}")
        print(body)
        sys.exit(1 if code >= 400 else 0)

    print(f"unknown op: {op}. use health | paths | curl")
    sys.exit(2)

if __name__ == "__main__":
    main()