import json
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from app.schemas.chat_dto import ChatRequest, ChatResponse
from app.services.agent_service import process_chat_message, process_chat_message_stream

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Standard REST API endpoint for chat.
    NestJS backend calls this endpoint to get a complete AI response.
    """
    reply = await process_chat_message(request.message, request.session_id)
    return ChatResponse(reply=reply)


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """
    SSE (Server-Sent Events) endpoint for streaming chat responses.
    NestJS backend proxies this to the frontend for real-time streaming.

    Flow: Frontend -> NestJS (POST) -> AI Service (SSE) -> NestJS (proxy SSE) -> Frontend
    """

    async def event_generator():
        async for chunk in process_chat_message_stream(
            request.message, request.session_id
        ):
            yield {"event": "message", "data": json.dumps({"chunk": chunk})}
        yield {"event": "done", "data": json.dumps({})}

    return EventSourceResponse(event_generator())
