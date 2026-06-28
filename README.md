# Memora AI Service

AI Microservice for Chatbot and Agents, built with **FastAPI**, **Google ADK (Agent Development Kit)**, and **LangChain**.

## Tech Stack
- **FastAPI**: Web framework for high-performance API endpoints.
- **Google ADK**: Framework for defining AI Agents and Workflow graphs.
- **LangChain**: Integration with LLMs, document loaders, and vector databases.
- **sse-starlette**: Server-Sent Events (SSE) support for streaming responses.

## Setup & Installation

1. Create and activate virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   Copy `.env` and fill in your API keys:
   ```bash
   GOOGLE_API_KEY="your_google_api_key"
   ```

4. Run the development server:
   ```bash
   python app/main.py
   ```
   The API will be available at `http://localhost:8000`.
   You can view the interactive API documentation (Swagger UI) at `http://localhost:8000/docs`.

## Integration Flow (SSE Streaming)
1. **Frontend (Next.js)** sends a request to **Backend (NestJS)**.
2. **Backend (NestJS)** makes a POST request to `http://localhost:8000/api/chat/stream`.
3. **AI Service (FastAPI)** streams chunks back to NestJS using Server-Sent Events (SSE).
4. **Backend (NestJS)** proxies the SSE stream directly back to the **Frontend** for real-time rendering.
