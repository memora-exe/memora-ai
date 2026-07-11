"""OpenAI-API-spec-only LLM dispatcher (refactored 2026-07-09).

Every provider (OpenAI, OpenRouter, Azure, Gemini via OpenAI-compat proxy,
Ollama, vLLM, …) speaks the same wire format: `Authorization: Bearer <key>`
+ `POST <base_url>/chat/completions`. So we use a single SDK — `ChatOpenAI`
from `langchain_openai` — and the env vars `OPENAI_BASE_URL` + `OPENAI_API_KEY`
decide where the request goes.

No abstract base class, no per-provider branches. To switch the model or
provider, change `OPENAI_MODEL` / `OPENAI_BASE_URL` / `OPENAI_API_KEY`. No
code change required.

Usage:
    from app.services.llm import get_chat_model, get_embedding_model

    chat = get_chat_model(temperature=0.2)
    chat = get_chat_model(temperature=0.1, override_model=settings.ROADMAP_MODEL)
    embeddings = get_embedding_model()
"""
from __future__ import annotations

from typing import Optional

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from app.core.config import settings


def get_chat_model(temperature: float = 0.2, override_model: Optional[str] = None) -> BaseChatModel:
    """Return a `ChatOpenAI` targeting whatever `OPENAI_BASE_URL` points at."""
    from langchain_openai import ChatOpenAI

    model_name = override_model or settings.OPENAI_MODEL
    if not settings.OPENAI_BASE_URL:
        raise ValueError(
            "OPENAI_BASE_URL is not set. Configure it in .env "
            "(e.g. https://api.openai.com/v1, or a Gemini-compatible proxy)."
        )
    if not settings.OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY is not set. Configure it in .env."
        )

    # Convention: OpenAI's API does not require `max_retries` or `timeout` here;
    # callers (http layer / langchain) handle retries. We keep this dumb on
    # purpose — the env vars are the strategy, not code.
    return ChatOpenAI(
        model=model_name,
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        temperature=temperature,
    )


def get_embedding_model() -> Embeddings:
    """Return an embedding model that also speaks the OpenAI `/v1/embeddings`
    wire format. Default uses `OPENAI_EMBED_BASE_URL` (falls back to the chat
    `OPENAI_BASE_URL`) and `OPENAI_EMBED_API_KEY` (falls back to chat key)."""
    from langchain_openai import OpenAIEmbeddings

    base_url = settings.OPENAI_EMBED_BASE_URL or settings.OPENAI_BASE_URL
    api_key = settings.OPENAI_EMBED_API_KEY or settings.OPENAI_API_KEY
    if not base_url or not api_key:
        raise ValueError(
            "Embeddings need an OpenAI-compatible base_url + api_key. "
            "Set OPENAI_BASE_URL/OPENAI_API_KEY or the *_EMBED_* overrides."
        )
    return OpenAIEmbeddings(
        model=settings.OPENAI_EMBED_MODEL,
        api_key=api_key,
        base_url=base_url,
    )
