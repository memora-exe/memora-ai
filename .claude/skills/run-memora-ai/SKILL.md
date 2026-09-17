---
name: run-memora-ai
description: Build, run, and drive the memora-ai FastAPI microservice. Use when asked to start the AI service, run its tests, hit its chat or search endpoints, or test Gemini integration on port 8000.
---

Memora-ai is the python AI microservice built with FastAPI, LangChain, and Google ADK. An agent drives it via the stdlib-only python driver `.claude/skills/run-memora-ai/driver.py` and reads its OpenAPI doc at `/docs`.

All paths below are relative to `memora-ai/`.

## Prerequisites

Windows 11, Python 3.10+ (already bundled in this box's environment, verified with `python`), and local running instances of PostgreSQL and Redis (typically from the main docker stack; see `run-be`).

A virtual environment (`venv/`) is expected at the unit root.

## Setup

First-time, to create the virtual environment and install packages:

```powershell
.\start.ps1   # self-healing PowerShell script that sets up venv and installs requirements.txt
```

If you do not want to run the PowerShell script, execute manually:

```bash
python -m venv venv
source venv/Scripts/activate   # or .\venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt
cp .env.example .env
```

Ensure `GOOGLE_API_KEY` is set in `.env` to allow Gemini API calls to succeed:

```bash
GOOGLE_API_KEY=your_gemini_api_key
```

## Run (agent path)

If the server isn't running on port 8000 yet, launch it:

```bash
# Activate the venv and start uvicorn
source venv/Scripts/activate
export PYTHONPATH=.
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Wait until Uvicorn displays `Application startup complete`. Smoke check the endpoints:

```bash
python .claude/skills/run-memora-ai/driver.py health
# OK   200  http://localhost:8000/health  '{"status":"healthy","service":"memora-ai"}'
# OK   200  http://localhost:8000/docs
```

List available paths:

```bash
python .claude/skills/run-memora-ai/driver.py paths
# 7 paths:
#   /api/chat/
#   /api/chat/stream
#   /api/chat/auto-title
#   /api/search
#   /api/node-insights/summary
#   /api/document-reader/summary
#   /health
```

Test a single endpoint:

```bash
python .claude/skills/run-memora-ai/driver.py curl GET /health
# status: 200
# {"status":"healthy","service":"memora-ai"}
```

| command | what it does |
|---|---|
| `health [baseUrl]` | GETs `/health`, `/docs`, `/openapi.json`; exits 1 if any return non-200 |
| `paths [baseUrl]` | Prints the 7 API paths defined in the OpenAPI schema |
| `curl <METHOD> <path> [baseUrl]` | Executes request; exits 1 on 4xx/5xx |

Docs (Swagger UI): <http://localhost:8000/docs>

## Run (human path)

```bash
.\start.ps1
# â†’ http://localhost:8000/docs in a browser
```

## Test

```bash
source venv/Scripts/activate
python test_api.py              # basic api sanity test
```

## Gotchas

- **Requires `PYTHONPATH` set.** If you run uvicorn without `PYTHONPATH=.` or exporting it, uvicorn will crash trying to import `app.main` with `ModuleNotFoundError: No module named 'app'`.
- **Relies on backing databases.** Even though it's a stateless microservice, `/api/search` and other endpoints may connect to PostgreSQL and Redis (session cache). Make sure the backend Docker stack is up.
- **Double slash in URL join.** The standard `urljoin` can sometimes produce `http://localhost:8000//health` depending on trailing slashes, but FastAPI handles double slashes gracefully.

## Troubleshooting

- **`EADDRINUSE 8000`**: port 8000 is occupied. Check via `netstat -ano | grep ":8000"` and stop the PID.
- **`ModuleNotFoundError: No module named 'psycopg2'`**: the venv install failed or was corrupted. Delete `venv/` and re-run `.\start.ps1` to trigger a clean rebuild.
- **`GOOGLE_API_KEY` errors**: the Gemini model calls will crash if the key is empty or invalid. Get a valid Gemini developer key and place it in `.env`.
