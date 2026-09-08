import json

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.clients.graph_client import GraphClient
from app.core.dependencies import get_embedding_service, get_graph_client, get_session_repo
from app.prompts.loader import render_prompt
from app.repositories.session_repository import SessionRepository
from app.schemas.chat import (
    AutoTitleRequest,
    AutoTitleResponse,
    ChatRequest,
    ChatResponse,
)
from app.services.chat.chat_service import (
    process_chat_message,
    process_chat_message_stream,
)
from app.services.embedding_service import EmbeddingService
from app.services.llm import get_chat_model

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    graph_client: GraphClient = Depends(get_graph_client),
    embedding_svc: EmbeddingService = Depends(get_embedding_service),
    session_repo: SessionRepository = Depends(get_session_repo),
):
    """Standard REST API endpoint for chat."""
    reply, tool_calls = await process_chat_message(
        message=request.message,
        session_id=request.session_id,
        project_id=request.project_id,
        jwt_token=request.jwt_token,
        graph_client=graph_client,
        embedding_svc=embedding_svc,
        session_repo=session_repo,
    )
    return ChatResponse(reply=reply, tool_calls=tool_calls)


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    graph_client: GraphClient = Depends(get_graph_client),
    embedding_svc: EmbeddingService = Depends(get_embedding_service),
    session_repo: SessionRepository = Depends(get_session_repo),
):
    """SSE endpoint for streaming chat responses."""

    async def event_generator():
        async for chunk in process_chat_message_stream(
            message=request.message,
            session_id=request.session_id,
            project_id=request.project_id,
            jwt_token=request.jwt_token,
            graph_client=graph_client,
            embedding_svc=embedding_svc,
            session_repo=session_repo,
        ):
            if isinstance(chunk, dict) and "metadata" in chunk:
                yield {"event": "message", "data": json.dumps({"metadata": chunk["metadata"]})}
            else:
                yield {"event": "message", "data": json.dumps({"chunk": chunk})}
        yield {"event": "done", "data": json.dumps({})}

    return EventSourceResponse(event_generator())


@router.post("/auto-title", response_model=AutoTitleResponse)
async def auto_title(request: AutoTitleRequest):
    """Generate a short chat-session title from the user's first message."""
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
        llm = get_chat_model(temperature=0.2)
        raw = await llm.ainvoke(prompt)
        text = (raw.content if hasattr(raw, "content") else str(raw)).strip()
    except Exception:
        text = msg.splitlines()[0][:60]

    text = text.strip().strip('"\'`').strip()
    text = text.splitlines()[0].strip()
    for prefix in ("Title:", "Tiêu đề:", "Tiêu đề :"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()

    if len(text) > 255:
        text = text[:255].rsplit(" ", 1)[0] or text[:255]

    return AutoTitleResponse(title=text or "Hội thoại mới")
