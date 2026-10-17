# Memora AI Service (LibIOG3 Stateless Technical Proxy)

Stateless gRPC Technical Proxy Service for Document Parsing, Embedding, Reranking, LLM Completion & Graph ML.

## Services & Ports
- **Protocol**: gRPC (Protobuf v1 in `proto/ai/v1/ai_service.proto`)
- **Default Port**: `50051`

## Architecture (LibIOG3)
- `app/ports/`: Domain port interfaces (`DocumentParserPort`, `EmbedderPort`, `RerankerPort`, `LlmPort`, `GraphMlPort`)
- `app/infrastructure/`: Concrete adapters & configuration
- `app/interfaces/grpc/`: gRPC servicers, interceptors, data mappers, and server entrypoint
- `proto/`: Protobuf definitions and generated stubs
- `tests/unit/`: Unit and integration test suite

## Quick Start

### PowerShell (Windows)
```powershell
.\start_grpc.ps1
```

### Bash (Linux/macOS)
```bash
./start_grpc.sh
```

### Direct Python
```bash
python main.py
```

### Running Tests
```bash
pytest tests/unit
```
