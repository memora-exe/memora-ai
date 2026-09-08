"""Per-session tool metadata tracker — extracted from agent_service.py.

Tracks mutation events (created/updated/deleted nodes/edges) and citation
data (citedNodes, chunks, reasoningPath) across a single chat turn so the
SSE stream can yield them as metadata at the end.
"""
from __future__ import annotations

_MUT_KEY = "mutatedEntities"

# Module-level registry: key = "project_id:session_id", value = tool result
_tool_metadata: dict[str, dict] = {}


def get_metadata(project_id: str, session_id: str) -> dict:
    """Get the tracked tool metadata for a project/session."""
    return _tool_metadata.get(f"{project_id}:{session_id}", {})


def clear_metadata(project_id: str, session_id: str) -> None:
    """Clear tracked metadata for a project/session."""
    _tool_metadata.pop(f"{project_id}:{session_id}", None)


def set_metadata(project_id: str, session_id: str, data: dict) -> None:
    """Replace the metadata for a project/session (used by hybrid search)."""
    _tool_metadata[f"{project_id}:{session_id}"] = data


def record_mutation(
    project_id: str,
    session_id: str,
    action: str,
    *,
    nodes: tuple | list = (),
    edges: tuple | list = (),
) -> None:
    """Append entity ids to the per-session mutation tracker.

    Called by tool_builder closures after successful graph write operations.
    """
    bucket = _tool_metadata.setdefault(
        f"{project_id}:{session_id}", {}
    ).setdefault(_MUT_KEY, {
        "created": {"nodes": [], "edges": []},
        "updated": {"nodes": [], "edges": []},
        "deleted": {"nodes": [], "edges": []},
    })
    # ponytail: UI-action buckets like `highlighted` aren't in the default
    # dict above — setdefault here lazy-creates them with the same shape so
    # llm_highlight (and any future tool) can extend without KeyError.
    bucket.setdefault(action, {"nodes": [], "edges": []})
    if nodes:
        bucket[action]["nodes"].extend(n for n in nodes if n)
    if edges:
        bucket[action]["edges"].extend(e for e in edges if e)


def build_citation_metadata(tool_result: dict) -> dict:
    """Build citation metadata from hybrid search tool result."""
    return {
        "citedNodes": tool_result.get("nodes", []),
        "citedEdges": tool_result.get("edges", []),
        "chunks": tool_result.get("chunks", []),
        "reasoningPath": tool_result.get("reasoningPath", []),
        "mutatedEntities": tool_result.get(_MUT_KEY, {
            "created": {"nodes": [], "edges": []},
            "updated": {"nodes": [], "edges": []},
            "deleted": {"nodes": [], "edges": []},
        }),
        "highlighted": tool_result.get(_MUT_KEY, {}).get(
            "highlighted", {"nodes": [], "edges": []}
        ),
    }
