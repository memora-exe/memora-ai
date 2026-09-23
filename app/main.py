import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api import router as api_router
from app.clients.nestjs_client import close_shared_nestjs_client
from app.core.config import settings
from app.services.ingestion.consumer import start_consumer


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start RabbitMQ consumer as a background task
    consumer_task = asyncio.create_task(start_consumer())
    yield
    # Shutdown: cancel consumer background task and close connection pool
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass
    await close_shared_nestjs_client()


app = FastAPI(
    title="Memora AI Service",
    description="AI Microservice for Chatbot and Agents - powered by Google ADK & LangChain",
    version="1.0.0",
    lifespan=lifespan,
)

# Allowed origins for CORS (default: FE 3000, BE 3010)
_allowed_origins_env = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:3010,http://127.0.0.1:3000,http://127.0.0.1:3010,http://103.178.234.132:3000,http://103.178.234.132:3010,http://103.178.234.132",
)
allowed_origins = [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|103\.178\.234\.132)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# Include API routes
app.include_router(api_router)


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "service": "memora-ai"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=False)
