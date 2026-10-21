# CLAUDE.md

Guidance for Claude Code when working in `memora-ai`.

## CI/CD Validation Rule (BẮT BUỘC - NGUYÊN TẮC TỐI CAO)

Mọi thay đổi code BẮT BUỘC phải chạy và pass 100% các bước CI:
- `pytest tests/unit` (hoặc `venv/Scripts/pytest.exe tests/unit` trên Windows). Toàn bộ tests phải pass.

## Testing policy

Unit & Integration tests are permitted. Validate functionality through:
- Unit tests for all 5 gRPC servicers, adapters, ports, and protobuf mappers (`tests/unit/test_grpc_services.py`).
- In-process loopback gRPC channels.
