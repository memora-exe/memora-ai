"""Chat processing service — extracted from agent_service.py.

Handles full responses (`process_chat_message`) and SSE streaming
(`process_chat_message_stream`). Manages timeouts, sessions, and citation
metadata.
"""
from __future__ import annotations

import asyncio
import json
import time

import httpx
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService, Session
from google.genai import types

from app.clients.graph_client import GraphClient
from app.clients.nestjs_client import NestJSClient
from app.common.logger.logger import get_logger
from app.core.config import settings
from app.repositories.session_repository import SessionRepository, session_repository
from app.services.chat.agent_factory import create_agent
from app.services.chat.metadata_tracker import (
    build_citation_metadata,
    clear_metadata,
    get_metadata,
)
from app.services.chat.stream_utils import aiter_with_timeout
from app.services.chat.thinking_filter import ThinkingStreamFilter, strip_thinking

logger = get_logger("ChatService")
APP_NAME = "memora"
_session_service = InMemorySessionService()

# Default clients — will be injected via Depends() in Phase 6
_default_nestjs = NestJSClient(settings.NESTJS_API_URL)
_default_graph = GraphClient(_default_nestjs)


async def _get_or_create_session(session_id: str) -> Session:
    existing = await _session_service.get_session(
        app_name=APP_NAME, user_id="default", session_id=session_id
    )
    if existing:
        return existing
    return await _session_service.create_session(
        app_name=APP_NAME, user_id="default", session_id=session_id
    )


async def process_chat_message(
    message: str,
    session_id: str,
    project_id: str,
    jwt_token: str,
    *,
    graph_client: GraphClient = None,
    session_repo: SessionRepository = None,
) -> tuple[str, dict]:
    """Process a chat message using the ADK Agent (full response)."""
    gc = graph_client or _default_graph
    sr = session_repo or session_repository

    logger.info(
        f"Chat started: session_id={session_id}, project_id={project_id}, "
        f"message={message[:50]}..."
    )
    try:
        await _get_or_create_session(session_id)
        clear_metadata(project_id, session_id)

        history = sr.get_messages(session_id) or []
        agent = create_agent(
            project_id, jwt_token, session_id, history,
            graph_client=gc,
        )
        runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
        runner.auto_create_session = True

        content = types.Content(parts=[types.Part(text=message)], role="user")
        sr.append_message(session_id, "user", message)

        final_response = ""
        try:
            async for event in aiter_with_timeout(
                runner.run_async(
                    user_id="default",
                    session_id=session_id,
                    new_message=content,
                ),
                timeout=settings.CHAT_LLM_TIMEOUT_SEC,
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    final_response = event.content.parts[0].text or ""
        except asyncio.TimeoutError:
            logger.error(
                f"Runner run_async timed out after {settings.CHAT_LLM_TIMEOUT_SEC}s "
                f"(session_id={session_id})"
            )
            final_response = (
                f"Sorry, the AI took too long to respond "
                f"(timeout after {settings.CHAT_LLM_TIMEOUT_SEC}s). Please try again."
            )

        tool_result = get_metadata(project_id, session_id)
        tool_calls = build_citation_metadata(tool_result)
        clear_metadata(project_id, session_id)

        if final_response:
            final_response = strip_thinking(final_response)
            if final_response:
                sr.append_message(session_id, "assistant", final_response)

        logger.info(f"Chat finished. Response length: {len(final_response)}")
        return (
            final_response or "Sorry, I could not process your request.",
            tool_calls,
        )
    except Exception as e:
        logger.error(f"Error in chat: {str(e)}", exc_info=True)
        raise e


async def process_chat_message_stream(
    message: str,
    session_id: str,
    project_id: str,
    jwt_token: str,
    *,
    graph_client: GraphClient = None,
    session_repo: SessionRepository = None,
):
    """Process a chat message and yield chunks for SSE."""
    gc = graph_client or _default_graph
    sr = session_repo or session_repository

    logger.info(
        f"Stream chat started: session_id={session_id}, project_id={project_id}, "
        f"message={message[:50]}..."
    )
    try:
        await _get_or_create_session(session_id)
        clear_metadata(project_id, session_id)

        history = sr.get_messages(session_id) or []
        agent = create_agent(
            project_id, jwt_token, session_id, history,
            graph_client=gc,
        )
        runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
        runner.auto_create_session = True

        content = types.Content(parts=[types.Part(text=message)], role="user")
        sr.append_message(session_id, "user", message)

        accumulated = ""
        event_count = 0
        stream_filter = ThinkingStreamFilter()
        turn_started = time.monotonic()
        task_id = f"{session_id}:{int(turn_started * 1000)}"
        logger.info(f"[chat] turn {task_id} started (project={project_id})")

        async def _runner_iter():
            run_config = RunConfig(streaming_mode=StreamingMode.SSE)
            async for event in aiter_with_timeout(
                runner.run_async(
                    user_id="default",
                    session_id=session_id,
                    new_message=content,
                    run_config=run_config,
                ),
                timeout=settings.CHAT_LLM_TIMEOUT_SEC,
            ):
                yield event

        try:
            async with asyncio.timeout(settings.CHAT_TURN_DEADLINE_SEC):
                async for event in _runner_iter():
                    event_count += 1
                    is_partial = getattr(event, "partial", False)
                    is_final = event.is_final_response() if hasattr(event, "is_final_response") else False

                    if event.content and event.content.parts:
                        text_chunk = event.content.parts[0].text or ""
                        if is_partial or (is_final and not accumulated):
                            accumulated += text_chunk
                            for filtered_chunk in stream_filter.process_chunk(text_chunk):
                                yield filtered_chunk

                for remaining_chunk in stream_filter.flush():
                    yield remaining_chunk
        except asyncio.TimeoutError:
            logger.error(
                f"[chat] turn {task_id} deadline {settings.CHAT_TURN_DEADLINE_SEC}s exceeded"
            )
            # Persist partial response on deadline
            clean_accumulated = strip_thinking(accumulated)
            if clean_accumulated:
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        r = await client.post(
                            f"{settings.NESTJS_API_URL}/projects/{project_id}/ai/sessions/{session_id}/persist",
                            headers={"Authorization": f"Bearer {jwt_token}"},
                            json={
                                "content": clean_accumulated,
                                "toolCalls": get_metadata(project_id, session_id),
                            },
                        )
                        logger.info(f"[chat] turn {task_id} persist on deadline: {r.status_code}")
                except Exception as _persist_err:
                    logger.warning(
                        f"[chat] turn {task_id} persist on deadline failed: {_persist_err}"
                    )
            yield {"error": f"turn deadline {settings.CHAT_TURN_DEADLINE_SEC}s exceeded"}
            return
        finally:
            logger.info(
                f"[chat] turn {task_id} done in {time.monotonic() - turn_started:.1f}s, "
                f"events={event_count}"
            )

        clean_accumulated = strip_thinking(accumulated)
        logger.info(f"Stream finished. Yielded {event_count} events. Clean response len: {len(clean_accumulated)}")

        tool_result = get_metadata(project_id, session_id)
        tool_calls = build_citation_metadata(tool_result)
        clear_metadata(project_id, session_id)

        # Yield metadata at end of stream
        yield {"metadata": tool_calls}

        if clean_accumulated:
            sr.append_message(session_id, "assistant", clean_accumulated)

    except Exception as e:
        logger.error(f"Error in stream chat: {str(e)}", exc_info=True)
        fallback_msg = (
            "Xin lỗi, đã xảy ra lỗi kết nối với mô hình AI. Vui lòng thử lại sau."
            if not accumulated
            else ""
        )
        if fallback_msg:
            yield fallback_msg
            sr.append_message(session_id, "assistant", fallback_msg)
        yield {"error": str(e)}
