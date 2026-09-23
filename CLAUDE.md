# CLAUDE.md

Guidance for Claude Code when working in `memora-ai`.

## CI/CD Validation Rule (BẮT BUỘC - NGUYÊN TẮC TỐI CAO)

Mọi thay đổi code BẮT BUỘC phải chạy và pass 100% các bước CI như trong `.github/workflows/cicd.yml`:
- `pytest` với `PORT: 3020` (hoặc `venv/Scripts/pytest.exe` trên Windows). Toàn bộ tests phải pass.

## Testing policy

Unit tests are permitted. Validate functionality through:
- Unit tests for isolated logic, utilities, and agent helpers.
- Direct API tests against running endpoints (e.g. `test_api.py`, curl, HTTP client requests).
- Acceptance tests covering end-to-end AI chat, graph traversal, and streaming workflows.
