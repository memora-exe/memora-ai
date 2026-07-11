# Memora AI Service

AI Microservice for Chatbot and Agents, built with **FastAPI**, **Google ADK (Agent Development Kit)**, and **LangChain**.

## Tech Stack
- **FastAPI**: Web framework for high-performance API endpoints.
- **Google ADK**: Framework for defining AI Agents and Workflow graphs.
- **LangChain**: Integration with LLMs, document loaders, and vector databases.
- **sse-starlette**: Server-Sent Events (SSE) support for streaming responses.

## Setup & Installation (PowerShell on Windows)

> Dự án cung cấp sẵn `start.ps1` — **chỉ cần 1 lệnh** để chạy toàn bộ.

1. Lần đầu tiên, cho phép chạy script PowerShell (một lần duy nhất):
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
   ```

2. Chạy server:
   ```powershell
   .\start.ps1
   ```

   Script sẽ tự động: tạo `venv\` (nếu chưa có) → cài `requirements.txt` → copy `.env.example` thành `.env` (nếu chưa có) → chạy `app/main.py`.

3. (Tuỳ chọn) Sửa `GOOGLE_API_KEY` trong file `.env`:
   ```env
   GOOGLE_API_KEY=your_google_api_key
   ```

### API sẽ chạy tại
- Base: `http://localhost:8000`
- Docs (Swagger UI): `http://localhost:8000/docs`

### Chạy thủ công (nếu không dùng `start.ps1`)

1. Tạo & kích hoạt môi trường ảo:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

2. Cài đặt dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

3. Cấu hình biến môi trường (copy `.env.example` thành `.env` rồi điền key):
   ```powershell
   Copy-Item .env.example .env
   ```

4. Chạy server:
   ```powershell
   python app/main.py
   ```

## Integration Flow (SSE Streaming)
1. **Frontend (Next.js)** sends a request to **Backend (NestJS)**.
2. **Backend (NestJS)** makes a POST request to `http://localhost:8000/api/chat/stream`.
3. **AI Service (FastAPI)** streams chunks back to NestJS using Server-Sent Events (SSE).
4. **Backend (NestJS)** proxies the SSE stream directly back to the **Frontend** for real-time rendering.
