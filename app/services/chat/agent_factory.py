"""ADK Agent factory — extracted from agent_service.py.

Constructs an Agent with instruction prompt (rendered with history) and
tools injected with project context.
"""
from __future__ import annotations

import os

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm

from app.clients.graph_client import GraphClient
from app.core.config import settings
from app.prompts.loader import render_prompt
from app.services.chat.tool_builder import build_graph_tools

INSTRUCTION_TEMPLATE = "chat_agent.md"

# Ensure API key is available in environ for LiteLLM / Gemini
if settings.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = settings.GOOGLE_API_KEY


def build_instruction(history_messages: list) -> str:
    """Load chat_agent.md template and inject last 20 history turns."""
    history_block = ""
    if history_messages:
        history_block = "\n## Prior conversation\n" + "\n".join(
            f"- {m['role']}: {m['content']}" for m in history_messages[-20:]
        )
    return render_prompt(INSTRUCTION_TEMPLATE, {"history_block": history_block})


def create_agent(
    project_id: str,
    jwt_token: str,
    session_id: str,
    history_messages: list,
    *,
    graph_client: GraphClient,
) -> Agent:
    """Create a new ADK Agent with tools injected with project context."""
    tools = build_graph_tools(
        project_id,
        jwt_token,
        session_id,
        graph_client=graph_client,
    )
    model_kwargs: dict = {}
    model_lower = settings.OPENAI_MODEL.lower()
    is_reasoning_model = any(m in model_lower for m in ["o1", "o3", "o4"])
    if not is_reasoning_model:
        model_kwargs["temperature"] = settings.AI_TEMPERATURE
    if settings.AI_REASONING_EFFORT:
        model_kwargs["reasoning_effort"] = settings.AI_REASONING_EFFORT
    model_kwargs["timeout"] = settings.CHAT_LLM_TIMEOUT_SEC
    model_kwargs["num_retries"] = 1

    return Agent(
        name="memora_assistant",
        model=LiteLlm(
            model=f"openai/{settings.OPENAI_MODEL}",
            api_base=settings.OPENAI_BASE_URL,
            api_key=settings.OPENAI_API_KEY,
            **model_kwargs,
        ),
        instruction=build_instruction(history_messages),
        tools=tools,
    )
