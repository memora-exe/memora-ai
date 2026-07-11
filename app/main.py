from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from app.api import router as api_router
from app.core.config import settings
from app.services.rabbitmq_consumer import start_consumer

app = FastAPI(
    title="Memora AI Service",
    description="AI Microservice for Chatbot and Agents - powered by Google ADK & LangChain",
    version="1.0.0",
)

# CORS middleware - allow NestJS backend to call this service
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your NestJS backend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)


@app.on_event("startup")
async def startup_event():
    # Start RabbitMQ consumer as a background asyncio task
    asyncio.create_task(start_consumer())


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "service": "memora-ai"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
