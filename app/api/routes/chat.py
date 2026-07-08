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
    Nhận project_id và jwt_token để AI có thể truy vấn graph data theo đúng phân quyền.
    """
    reply, tool_calls = await process_chat_message(
        message=request.message,
        session_id=request.session_id,
        project_id=request.project_id,
        jwt_token=request.jwt_token,
    )
    return ChatResponse(reply=reply, tool_calls=tool_calls)


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """
    SSE (Server-Sent Events) endpoint for streaming chat responses.
    NestJS backend proxies this to the frontend for real-time streaming.

    Flow: Frontend -> NestJS (POST) -> AI Service (SSE) -> NestJS (proxy SSE) -> Frontend
    """

    async def event_generator():
        async for chunk in process_chat_message_stream(
            message=request.message,
            session_id=request.session_id,
            project_id=request.project_id,
            jwt_token=request.jwt_token,
        ):
            # Detect metadata dict yielded at end of stream
            if isinstance(chunk, dict) and "metadata" in chunk:
                yield {"event": "message", "data": json.dumps({"metadata": chunk["metadata"]})}
            else:
                yield {"event": "message", "data": json.dumps({"chunk": chunk})}
        yield {"event": "done", "data": json.dumps({})}

    return EventSourceResponse(event_generator())
