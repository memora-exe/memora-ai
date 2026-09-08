"""Backward-compatibility shim — re-exports from app.services.chat.*.

This file will be deleted in Phase 6 after all imports are updated.
"""
from app.services.chat.chat_service import (
    process_chat_message,
    process_chat_message_stream,
)
from app.services.chat.metadata_tracker import (
    build_citation_metadata as _build_citation_metadata,
    clear_metadata as _clear_metadata,
    get_metadata as _get_metadata,
)
from app.services.chat.tool_builder import build_graph_tools as _build_graph_tools

__all__ = [
    "process_chat_message",
    "process_chat_message_stream",
    "_build_graph_tools",
    "_get_metadata",
    "_clear_metadata",
    "_build_citation_metadata",
]
