import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from app.core.config import settings
from app.prompts.loader import render_prompt
from app.schemas.chat_dto import ChatRequest, ChatResponse
from app.services.agent_service import process_chat_message, process_chat_message_stream
from app.services.llm import get_chat_model

router = APIRouter(prefix="/api/chat", tags=["Chat"])


class AutoTitleRequest(BaseModel):
    message: str
    project_id: str
    jwt_token: str = ""


class AutoTitleResponse(BaseModel):
    title: str


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


@router.post("/auto-title", response_model=AutoTitleResponse)
async def auto_title(request: AutoTitleRequest):
    """
    Generate a short chat-session title from the user's first message.
    Called by the NestJS backend after the first user message lands.
    """
    msg = (request.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="message is required")

    try:
        prompt = render_prompt(
            "chat_title_generator.md",
            {"message": msg[:500]},
        )
    except FileNotFoundError:
        prompt = (
            "Generate a short title (max 6 words, same language as the user) "
            f"for this chat: {msg[:500]}\nTitle:"
        )

    try:
        llm = get_chat_model(temperature=0.2, override_model=settings.SUMMARY_MODEL)
        raw = await llm.ainvoke(prompt)
        text = (raw.content if hasattr(raw, "content") else str(raw)).strip()
    except Exception:
        # Fallback: truncate the message itself as a title.
        text = msg.splitlines()[0][:60]

    # Strip quotes/backticks/leading bullet decoration
    text = text.strip().strip('"\'`').strip()
    # Take only the first line in case the model added explanation
    text = text.splitlines()[0].strip()
    # Remove common prefixes
    for prefix in ("Title:", "Tiêu đề:", "Tiêu đề :"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()

    if len(text) > 255:
        text = text[:255].rsplit(" ", 1)[0] or text[:255]

    return AutoTitleResponse(title=text or "Hội thoại mới")
