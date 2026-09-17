"""OpenAI-API-spec-only LLM dispatcher (refactored 2026-07-09).

Every provider (OpenAI, OpenRouter, Azure, Gemini via OpenAI-compat proxy,
Ollama, vLLM, ...) speaks the same wire format: `Authorization: Bearer <key>`
+ `POST <base_url>/chat/completions`. So we use a single SDK - `ChatOpenAI`
from `langchain_openai` - and the env vars `OPENAI_BASE_URL` + `OPENAI_API_KEY`
decide where the request goes.

No abstract base class, no per-provider branches. To switch the model or
provider, change `OPENAI_MODEL` / `OPENAI_BASE_URL` / `OPENAI_API_KEY`. No
code change required.

Usage:
    from app.services.llm import get_chat_model

    chat = get_chat_model(temperature=0.2)
"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from app.core.config import settings


def get_chat_model(temperature: float = 0.2) -> BaseChatModel:
    """Return a `ChatOpenAI` targeting whatever `OPENAI_BASE_URL` points at.

    A single `OPENAI_MODEL` is used across the whole app - no per-task overrides.
    Change `OPENAI_MODEL` in `.env` to switch models.
    """
    from langchain_openai import ChatOpenAI

    if not settings.OPENAI_BASE_URL:
        raise ValueError(
            "OPENAI_BASE_URL is not set. Configure it in .env "
            "(e.g. https://api.openai.com/v1, or a Gemini-compatible proxy)."
        )
    if not settings.OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY is not set. Configure it in .env."
        )

    # Convention: keep this dumb on purpose - the env vars are the strategy, not code.
    return ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        temperature=temperature,
    )
