"""Common LLM response parsing — deduplicated from 4+ call sites.

Usage:
    from app.services.llm.response_parser import parse_llm_json

    data = parse_llm_json(raw_response, fallback={"nodes": [], "edges": []})
"""
from __future__ import annotations

import json
import re


def extract_text(raw_response) -> str:
    """Pull the text content from a LangChain AIMessage or string."""
    text = raw_response.content if hasattr(raw_response, "content") else str(raw_response)
    return text.strip()


def strip_json_fences(text: str) -> str:
    """Remove ```json ... ``` fences the model may add."""
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


def parse_llm_json(raw_response, *, fallback: dict | None = None) -> dict:
    """Extract content → strip → remove fences → json.loads → fallback.

    Args:
        raw_response: LangChain AIMessage or string.
        fallback: returned on parse failure. Defaults to {}.
    """
    if fallback is None:
        fallback = {}
    text = extract_text(raw_response)
    text = strip_json_fences(text)
    # Find the first JSON object in the text (model may add explanation around it)
    match = re.search(r"\{[\s\S]*\}", text)
    payload = match.group(0) if match else text
    try:
        return json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return fallback
