import asyncio
import json
import os

import httpx
from google.genai import types
from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.adk.sessions import Session, InMemorySessionService
from app.common.logger.logger import get_logger
from app.core.config import settings
from app.services.session_manager import session_manager
from app.services.graph_tools import (
    get_project_nodes,
    get_project_edges,
    query_project_graph,
    traverse_project_graph,
    llm_search_by_embedding,
    llm_hybrid_search,
    create_project_node,
    update_project_node,
    delete_project_node,
    create_project_edge,
    update_project_edge,
    delete_project_edge,
    list_project_node_types,
    list_project_files,
    read_file_content,
    llm_highlight_nodes,
    llm_highlight_edges,
)
from app.prompts.loader import render_prompt

logger = get_logger("AgentService")

INSTRUCTION = "chat_agent.md"


def _build_instruction(history_messages: list) -> str:
    """Load chat_agent.md template and inject last 20 history turns."""
    history_block = ""
    if history_messages:
        history_block = "\n## Prior conversation\n" + "\n".join(
            f"- {m['role']}: {m['content']}" for m in history_messages[-20:]
        )
    return render_prompt(INSTRUCTION, {"history_block": history_block})


# Đảm bảo API key được set cho Gemini model
if settings.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = settings.GOOGLE_API_KEY

app_name = "memora"
session_service = InMemorySessionService()

# Module-level metadata tracking: key = "project_id:session_id", value = tool result
_tool_metadata: dict = {}
_MUT_KEY = "mutatedEntities"


def _get_metadata(project_id: str, session_id: str) -> dict:
    """Get the tracked tool metadata for a project/session."""
    return _tool_metadata.get(f"{project_id}:{session_id}", {})


def _clear_metadata(project_id: str, session_id: str) -> None:
    """Clear tracked metadata for a project/session."""
    _tool_metadata.pop(f"{project_id}:{session_id}", None)


def _build_citation_metadata(tool_result: dict) -> dict:
    """Build citation metadata from hybrid search tool result."""
    return {
        "citedNodes":      tool_result.get("nodes", []),
        "citedEdges":      tool_result.get("edges", []),
        "chunks":          tool_result.get("chunks", []),
        "reasoningPath":   tool_result.get("reasoningPath", []),
        "mutatedEntities": tool_result.get(_MUT_KEY, {
            "created": {"nodes": [], "edges": []},
            "updated": {"nodes": [], "edges": []},
            "deleted": {"nodes": [], "edges": []},
        }),
        "highlighted":     tool_result.get(_MUT_KEY, {}).get("highlighted", {"nodes": [], "edges": []}),
    }


def _build_graph_tools(project_id: str, jwt_token: str, session_id: str) -> list:
    """
    Tạo danh sách tools cho Agent, đã inject sẵn project_id và jwt_token.
    LLM chỉ cần gọi tool theo nghiệp vụ, không cần biết về project_id hay jwt_token.
    """

    def _record_mutation(action: str, *, nodes=(), edges=()) -> None:
        """Append entity ids to the per-session mutation tracker.

        project_id, session_id and _tool_metadata are captured from the enclosing
        scope of _build_graph_tools (per-turn closure).
        """
        bucket = _tool_metadata.setdefault(
            f"{project_id}:{session_id}", {}
        ).setdefault(_MUT_KEY, {
            "created": {"nodes": [], "edges": []},
            "updated": {"nodes": [], "edges": []},
            "deleted": {"nodes": [], "edges": []},
        })
        # ponytail: UI-action buckets like `highlighted` aren't in the default
        # dict above — `setdefault` here lazy-creates them with the same shape so
        # `llm_highlight` (and any future tool) can extend without KeyError.
        bucket.setdefault(action, {"nodes": [], "edges": []})
        if nodes:
            bucket[action]["nodes"].extend(n for n in nodes if n)
        if edges:
            bucket[action]["edges"].extend(e for e in edges if e)

    def llm_get_all_nodes() -> dict:
        """Retrieve all knowledge graph nodes in the current project.
        Use this tool when the user asks about existing nodes, concepts, or entities in the project.

        Returns:
            dict: A list of all nodes with their properties (id, name, type, metadata, etc.).
        """
        return get_project_nodes(project_id, jwt_token)

    def llm_get_all_edges() -> dict:
        """Retrieve all edges (relationships) between nodes in the current project.
        Use this tool when the user asks about connections, relationships, or links between entities.

        Returns:
            dict: A list of all edges with their properties (id, sourceNodeId, targetNodeId, type, etc.).
        """
        return get_project_edges(project_id, jwt_token)

    def llm_query_graph(node_type_ids: list = None, edge_type_ids: list = None) -> dict:
        """Query specific parts of the project graph using optional filters on node types or edge types.
        Use this when the user wants to filter graph data by a specific category or type.

        Args:
            node_type_ids (list): Optional list of node type IDs to filter nodes by type.
            edge_type_ids (list): Optional list of edge type IDs to filter edges by type.

        Returns:
            dict: Filtered graph result containing matched nodes and edges.
        """
        query_params = {}
        if node_type_ids:
            query_params["nodeTypeIds"] = node_type_ids
        if edge_type_ids:
            query_params["edgeTypeIds"] = edge_type_ids
        return query_project_graph(project_id, jwt_token, query_params)

    def llm_traverse_graph(start_node_id: str, depth: int = 3) -> dict:
        """Traverse the knowledge graph starting from a specific node up to a given depth.
        Use this when the user wants to explore what is connected to a specific node.

        Args:
            start_node_id (str): The ID of the starting node.
            depth (int): Maximum traversal depth. Default is 3.

        Returns:
            dict: Subgraph containing all reachable nodes and edges within the specified depth.
        """
        return traverse_project_graph(project_id, jwt_token, start_node_id, depth)

    def llm_search_vector(query: str, k: int = 5) -> list:
        """Search document chunks using semantic similarity (pgvector) in a project.
        Use this tool when the user asks a question that requires scanning document contents, searching for details, or doing semantic lookup.
        """
        return llm_search_by_embedding(project_id, query, k)

    def llm_search_hybrid(query: str, k: int = 5) -> dict:
        """Hybrid search combining semantic search on document chunks and graph nodes.
        Use this tool when the user asks a complex question that requires both concept relationships and document contents.
        """
        result = llm_hybrid_search(project_id, query, jwt_token, k)
        # Track the tool result for citation metadata
        _tool_metadata[f"{project_id}:{session_id}"] = result
        return result

    def llm_create_node(
        node_name: str,
        node_type_id: str = None,
        node_id: str = None,
        note: str = None,
        data: dict = None,
    ) -> dict:
        """Create a new knowledge graph node in current project.

        Use when the user asks to capture a new concept, entity, person, or topic
        in the project. Populate `note` with the substantive text (an excerpt,
        summary, or analysis) and `data` with structured metadata such as
        {"source": fileId} when the node was derived from a file.

        Args:
            node_name: display name for the new node (REQUIRED).
            node_type_id: existing node type id (UUID) to assign — omitted = no type.
            node_id: optional client-provided UUID; server assigns one when omitted.
            note: substantive text content for the node's note field (REQUIRED
                when the user shared a file or asked for the node to contain
                information; never leave empty in those cases).
            data: optional structured payload (e.g. {"source": "<fileId>"}).

        Returns: created node with server-assigned id and properties.
        """
        payload = {"nodeName": node_name}
        if node_type_id:
            payload["nodeTypeId"] = node_type_id
        if node_id:
            payload["nodeId"] = node_id
        if note:
            payload["note"] = note
        if data:
            payload["data"] = data
        result = create_project_node(project_id, jwt_token, payload)
        nid = None
        if isinstance(result, dict) and not result.get("error"):
            nid = result.get("nodeId") or result.get("id")
        if nid:
            _record_mutation("created", nodes=[nid])
        return result

    def llm_update_node(
        node_id: str,
        node_name: str = None,
        node_type_id: str = None,
        note: str = None,
        data: dict = None,
    ) -> dict:
        """Update an existing knowledge graph node in current project.

        Omit any field to keep its current value. Pass `note` to overwrite the
        text content; pass `data` to overwrite the structured payload.
        """
        payload = {"nodeId": node_id}
        if node_name is not None:
            payload["nodeName"] = node_name
        if node_type_id is not None:
            payload["nodeTypeId"] = node_type_id
        if note is not None:
            payload["note"] = note
        if data is not None:
            payload["data"] = data
        result = update_project_node(project_id, jwt_token, payload)
        if isinstance(result, dict) and not result.get("error"):
            _record_mutation("updated", nodes=[node_id])
        return result

    def llm_update_node_note(node_id: str, note: str) -> dict:
        """Convenience wrapper to set only the `note` field of an existing node.

        Use when the user asks to attach text to an existing concept (e.g. "ghi
        chú cho node X là: ...").
        """
        return llm_update_node(node_id=node_id, note=note)

    def llm_delete_node(node_id: str) -> dict:
        """Delete a knowledge graph node from the current project.
        Use this when the user explicitly asks to remove a node.
        This action is irreversible and will also remove all edges connected to the node.

        Args:
            node_id (str): The ID of the node to delete.

        Returns:
            dict: Confirmation with the deleted node's ID on success, or error details.
        """
        result = delete_project_node(project_id, jwt_token, node_id)
        if isinstance(result, dict) and not result.get("error"):
            _record_mutation("deleted", nodes=[node_id])
        return result

    def llm_list_files() -> dict:
        """List all files uploaded to the current project.
        Use this whenever the user mentions 'the file', 'document', 'report', 'PDF',
        or refers to a file without giving its name. Returns a dict with a list of
        {id, originalName, mimetype, size, ...} entries.
        """
        return list_project_files(project_id, jwt_token)

    def llm_read_file(file_id: str) -> dict:
        """Read parsed text content of a single uploaded file by its id.
        Use after llm_list_files to retrieve a specific file's content.
        """
        return read_file_content(project_id, file_id, jwt_token)

    def llm_create_edge(
        source_node_id: str,
        target_node_id: str,
        edge_type_id: str = None,
        properties: dict = None,
        edge_id: str = None,
    ) -> dict:
        """Create a relationship between two existing nodes in the project.

        Use when the user describes a relation between two concepts they already
        know (or that you just created). Source and target must be nodeIds of
        nodes that already exist in this project; use llm_search_hybrid first if
        you are unsure.

        Args:
            source_node_id: id of the source node (REQUIRED).
            target_node_id: id of the target node (REQUIRED).
            edge_type_id: optional edge type id (UUID) — use llm_list_node_types
                only after we also add list_edge_types; for now omit unless told.
            properties: optional structured payload (free dict of metadata).
            edge_id: optional client-provided UUID; server assigns one if omitted.
        """
        payload = {"sourceNodeId": source_node_id, "targetNodeId": target_node_id}
        if edge_type_id:
            payload["edgeTypeId"] = edge_type_id
        if properties:
            payload["properties"] = properties
        if edge_id:
            payload["edgeId"] = edge_id
        result = create_project_edge(project_id, jwt_token, payload)
        eid = None
        if isinstance(result, dict) and not result.get("error"):
            eid = result.get("edgeId") or result.get("id")
        if eid:
            _record_mutation("created", edges=[eid])
        return result

    def llm_update_edge(
        edge_id: str,
        source_node_id: str = None,
        target_node_id: str = None,
        edge_type_id: str = None,
        properties: dict = None,
    ) -> dict:
        """Update an existing edge. Omit any field to keep its current value."""
        payload = {"edgeId": edge_id}
        if source_node_id is not None:
            payload["sourceNodeId"] = source_node_id
        if target_node_id is not None:
            payload["targetNodeId"] = target_node_id
        if edge_type_id is not None:
            payload["edgeTypeId"] = edge_type_id
        if properties is not None:
            payload["properties"] = properties
        result = update_project_edge(project_id, jwt_token, payload)
        if isinstance(result, dict) and not result.get("error"):
            _record_mutation("updated", edges=[edge_id])
        return result

    def llm_delete_edge(edge_id: str) -> dict:
        """Delete an edge by id."""
        result = delete_project_edge(project_id, jwt_token, edge_id)
        if isinstance(result, dict) and not result.get("error"):
            _record_mutation("deleted", edges=[edge_id])
        return result

    def llm_list_node_types() -> dict:
        """List all node types defined in the current project.

        Use when you need a nodeTypeId for llm_create_node / llm_update_node.
        Returns the array of node type entries: each has nodeTypeId, typeName,
        and optional schema. Pick the most specific existing type; do NOT invent
        a new id — if no type fits, omit nodeTypeId.
        """
        return list_project_node_types(project_id, jwt_token)

    def llm_highlight(nodes_or_edges: str = "nodes", ids: list = None) -> dict:
        """UI-only highlight. Pass `nodes_or_edges` ∈ {nodes, edges} and `ids` list.

        Wraps the stateless `llm_highlight_nodes`/`llm_highlight_edges` from
        graph_tools with the closure-captured _record_mutation so ids show up in
        meta.mutatedEntities.highlighted and propagate to FE searchHighlightIds.
        """
        kind = (nodes_or_edges or "nodes").lower()
        clean_ids = [str(i) for i in (ids or []) if i]
        if not clean_ids:
            return {"error": "no ids provided", "_highlight": {"action": "highlighted", "kind": kind, "ids": []}}
        _record_mutation("highlighted", **{kind: clean_ids})
        return {"highlighted_nodes": clean_ids} if kind == "nodes" else {"highlighted_edges": clean_ids}

    return [
        llm_get_all_nodes,
        llm_get_all_edges,
        llm_query_graph,
        llm_traverse_graph,
        llm_search_vector,
        llm_search_hybrid,
        llm_create_node,
        llm_update_node,
        llm_update_node_note,
        llm_delete_node,
        llm_create_edge,
        llm_update_edge,
        llm_delete_edge,
        llm_list_node_types,
        llm_list_files,
        llm_read_file,
        llm_highlight,
    ]


def _create_agent(
    project_id: str,
    jwt_token: str,
    session_id: str,
    history_messages: list,
) -> Agent:
    """Tạo một Agent mới với tools được inject context cho project.

    history_messages: list of {role, content} dicts loaded from Redis by the caller.
    The chat_agent.md template (P1) defines node-vs-file vocabulary; history is
    appended by _build_instruction.
    """
    tools = _build_graph_tools(project_id, jwt_token, session_id)
    return Agent(
        name="memora_assistant",
        model=LiteLlm(
            model=f"openai/{settings.OPENAI_MODEL}",
            api_base=settings.OPENAI_BASE_URL,
            api_key=settings.OPENAI_API_KEY,
        ),
        instruction=_build_instruction(history_messages),
        tools=tools,
    )


async def _get_or_create_session(session_id: str) -> Session:
    """Lấy session có sẵn hoặc tạo mới nếu chưa tồn tại."""
    existing = await session_service.get_session(
        app_name=app_name, user_id="default", session_id=session_id
    )
    if existing:
        return existing
    return await session_service.create_session(
        app_name=app_name,
        user_id="default",
        session_id=session_id,
    )


async def _aiter_with_timeout(async_iter, timeout: float):
    """Wrap any async iterator with a per-step timeout. Raises asyncio.TimeoutError
    if a single __anext__() exceeds `timeout` seconds. Use this instead of
    `asyncio.wait_for(iter, timeout=...)` because the latter wraps the coroutine
    returned by the call, not the per-step await — and `async for` rejects a
    plain coroutine with TypeError.
    ponytail: replace with a context-manager timeout if we need an overall
    deadline (currently we only need idle-timeout protection).
    """
    iterator = async_iter.__aiter__()
    while True:
        try:
            yield await asyncio.wait_for(iterator.__anext__(), timeout=timeout)
        except StopAsyncIteration:
            return


async def process_chat_message(
    message: str, session_id: str, project_id: str, jwt_token: str
) -> tuple[str, dict]:
    """
    Process a chat message using the ADK Agent (full response).
    Agent được tạo động với tools đã inject project_id và jwt_token.
    """
    logger.info(f"Chat started: session_id={session_id}, project_id={project_id}, message={message[:50]}...")
    try:
        session = await _get_or_create_session(session_id)

        _clear_metadata(project_id, session_id)
        history_messages = session_manager.get_messages(session_id) or []
        agent = _create_agent(project_id, jwt_token, session_id, history_messages)
        runner = InMemoryRunner(agent=agent, app_name=app_name)
        runner.auto_create_session = True

        content = types.Content(parts=[types.Part(text=message)], role="user")

        session_manager.append_message(session_id, "user", message)

        final_response = ""
        try:
            async for event in _aiter_with_timeout(
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
            logger.error(f"Runner run_async timed out after {settings.CHAT_LLM_TIMEOUT_SEC}s (session_id={session_id})")
            final_response = (
                f"Sorry, the AI took too long to respond "
                f"(timeout after {settings.CHAT_LLM_TIMEOUT_SEC}s). Please try again."
            )

        tool_result = _get_metadata(project_id, session_id)
        tool_calls = _build_citation_metadata(tool_result)
        _clear_metadata(project_id, session_id)

        if final_response:
            session_manager.append_message(session_id, "assistant", final_response)

        logger.info(f"Chat finished. Response length: {len(final_response)}")
        return (final_response if final_response else "Sorry, I could not process your request.", tool_calls)
    except Exception as e:
        logger.error(f"Error in chat: {str(e)}", exc_info=True)
        raise e


async def process_chat_message_stream(
    message: str, session_id: str, project_id: str, jwt_token: str
):
    """
    Process a chat message and yield chunks for SSE (Server-Sent Events).
    Agent được tạo động với tools đã inject project_id và jwt_token.
    """
    logger.info(f"Stream chat started: session_id={session_id}, project_id={project_id}, message={message[:50]}...")
    try:
        session = await _get_or_create_session(session_id)

        _clear_metadata(project_id, session_id)
        history_messages = session_manager.get_messages(session_id) or []
        agent = _create_agent(project_id, jwt_token, session_id, history_messages)
        runner = InMemoryRunner(agent=agent, app_name=app_name)
        runner.auto_create_session = True

        content = types.Content(parts=[types.Part(text=message)], role="user")

        session_manager.append_message(session_id, "user", message)

        accumulated = ""
        event_count = 0
        try:
            # ponytail: outer `wait_for` provides an OVERALL turn deadline.
            # The inner `_aiter_with_timeout` only protects between events; if
            # the runner is parked inside one tool HTTP call (e.g. llm_search_hybrid
            # against a starved LiteLLM pool during file ingestion), per-step never
            # fires. `CHAT_TURN_DEADLINE_SEC` is the hard ceiling so the SSE stream
            # always ends — yields error JSON then [DONE] on timeout.
            import time as _time
            turn_started = _time.monotonic()
            task_id = f"{session_id}:{int(turn_started*1000)}"
            logger.info(f"[chat] turn {task_id} started (project={project_id})")

            async def _runner_iter():
                async for event in _aiter_with_timeout(
                    runner.run_async(
                        user_id="default",
                        session_id=session_id,
                        new_message=content,
                    ),
                    timeout=settings.CHAT_LLM_TIMEOUT_SEC,
                ):
                    yield event

            try:
                # ponytail: asyncio.wait_for() returns a coroutine, not an async
                # iterator — `async for` over it raised TypeError and aborted every
                # stream. asyncio.timeout() (Py 3.11+) scopes the deadline to the
                # loop body so the iterator drains normally and raises TimeoutError
                # on exit instead.
                async with asyncio.timeout(settings.CHAT_TURN_DEADLINE_SEC):
                    async for event in _runner_iter():
                        event_count += 1
                        if event.content:
                            parts = event.content.parts
                            if parts:
                                text_chunk = parts[0].text or ""
                                accumulated += text_chunk
                                yield text_chunk
            except asyncio.TimeoutError as _turn_deadline:
                logger.error(
                    f"[chat] turn {task_id} deadline {settings.CHAT_TURN_DEADLINE_SEC}s exceeded"
                )
                # ponytail: Bug 2 — on the deadline path, `stream.on('end')` on the
                # BE side won't fire (the deadline happens in our `_runner_iter`,
                # BE only sees a mid-stream abort). Persist whatever we accumulated
                # so the user sees partial progress on reload. Fire-and-forget httpx
                # so the SSE path can close immediately. The local `if accumulated`
                # guards against empty/blank messages that would create empty rows.
                if accumulated:
                    try:
                        async with httpx.AsyncClient(timeout=10) as client:
                            r = await client.post(
                                f"{settings.NESTJS_API_URL}/projects/{project_id}/ai/sessions/{session_id}/persist",
                                headers={"Authorization": f"Bearer {jwt_token}"},
                                json={"content": accumulated, "toolCalls": _get_metadata(project_id, session_id)},
                            )
                            logger.info(f"[chat] turn {task_id} persist on deadline: {r.status_code}")
                    except Exception as _persist_err:
                        logger.warning(f"[chat] turn {task_id} persist on deadline failed (non-fatal): {_persist_err}")
                yield json.dumps({"error": f"turn deadline {settings.CHAT_TURN_DEADLINE_SEC}s exceeded"})
                return
            finally:
                logger.info(
                    f"[chat] turn {task_id} done in {_time.monotonic()-turn_started:.1f}s, events={event_count}"
                )
        except asyncio.TimeoutError:
            logger.error(f"Runner run_async timed out after {settings.CHAT_LLM_TIMEOUT_SEC}s (session_id={session_id})")
            yield json.dumps({"error": f"LLM timed out after {settings.CHAT_LLM_TIMEOUT_SEC}s"})
            return

        logger.info(f"Stream finished. Yielded {event_count} events. Response len: {len(accumulated)}")

        tool_result = _get_metadata(project_id, session_id)
        tool_calls = _build_citation_metadata(tool_result)
        _clear_metadata(project_id, session_id)

        # Yield the metadata at the end of the stream
        yield {"metadata": tool_calls}

        if accumulated:
            session_manager.append_message(session_id, "assistant", accumulated)
    except Exception as e:
        logger.error(f"Error in stream chat: {str(e)}", exc_info=True)
        raise e

