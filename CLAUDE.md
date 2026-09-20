# CLAUDE.md

Guidance for Claude Code when working in `memora-ai`.

## Testing policy

Unit tests are permitted. Validate functionality through:
- Unit tests for isolated logic, utilities, and agent helpers.
- Direct API tests against running endpoints (e.g. `test_api.py`, curl, HTTP client requests).
- Acceptance tests covering end-to-end AI chat, graph traversal, and streaming workflows.
