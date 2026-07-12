import asyncio
import os
from google.genai import types
from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.adk.sessions import Session, InMemorySessionService
from google.adk.events.event import Event
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
)

logger = get_logger("AgentService")

# Đảm bảo API key được set cho Gemini model
if settings.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = settings.GOOGLE_API_KEY

app_name = "memora"
session_service = InMemorySessionService()

# Module-level metadata tracking: key = "project_id:session_id", value = tool result
_tool_metadata: dict = {}


def _get_metadata(project_id: str, session_id: str) -> dict:
    """Get the tracked tool metadata for a project/session."""
    return _tool_metadata.get(f"{project_id}:{session_id}", {})


def _clear_metadata(project_id: str, session_id: str) -> None:
    """Clear tracked metadata for a project/session."""
    _tool_metadata.pop(f"{project_id}:{session_id}", None)


def _build_citation_metadata(tool_result: dict) -> dict:
    """Build citation metadata from hybrid search tool result."""
    return {
        "citedNodes": tool_result.get("nodes", []),
        "citedEdges": tool_result.get("edges", []),
        "chunks": tool_result.get("chunks", []),
        "reasoningPath": tool_result.get("reasoningPath", []),
    }


def _build_graph_tools(project_id: str, jwt_token: str, session_id: str) -> list:
    """
    Tạo danh sách tools cho Agent, đã inject sẵn project_id và jwt_token.
    LLM chỉ cần gọi tool theo nghiệp vụ, không cần biết về project_id hay jwt_token.
    """

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

    def llm_create_node(node_name: str, node_type_id: str = None, node_id: str = None) -> dict:
        """Create a new knowledge graph node in the current project.
        Use this tool when the user asks to add a new concept, entity, person, or topic to the project.

        Args:
            node_name (str): The display name for the new node.
            node_type_id (str, optional): The ID of an existing node type to assign.
            node_id (str, optional): Client-provided UUID for the node. If omitted, server assigns one.

        Returns:
            dict: The created node with its server-assigned ID and properties.
        """
        payload = {"nodeName": node_name}
        if node_type_id:
            payload["nodeTypeId"] = node_type_id
        if node_id:
            payload["nodeId"] = node_id
        return create_project_node(project_id, jwt_token, payload)

    def llm_update_node(node_id: str, node_name: str = None, node_type_id: str = None) -> dict:
        """Update an existing knowledge graph node in the current project.
        Use this when the user asks to rename a node or change its type.

        Args:
            node_id (str): The ID of the node to update.
            node_name (str, optional): New display name. Omit to keep current.
            node_type_id (str, optional): New node type ID. Omit to keep current.

        Returns:
            dict: The updated node.
        """
        payload = {"nodeId": node_id}
        if node_name is not None:
            payload["nodeName"] = node_name
        if node_type_id is not None:
            payload["nodeTypeId"] = node_type_id
        return update_project_node(project_id, jwt_token, payload)

    def llm_delete_node(node_id: str) -> dict:
        """Delete a knowledge graph node from the current project.
        Use this when the user explicitly asks to remove a node.
        This action is irreversible and will also remove all edges connected to the node.

        Args:
            node_id (str): The ID of the node to delete.

        Returns:
            dict: Confirmation with the deleted node's ID on success, or error details.
        """
        return delete_project_node(project_id, jwt_token, node_id)

    return [
        llm_get_all_nodes,
        llm_get_all_edges,
        llm_query_graph,
        llm_traverse_graph,
        llm_search_vector,
        llm_search_hybrid,
        llm_create_node,
        llm_update_node,
        llm_delete_node,
    ]


def _create_agent(project_id: str, jwt_token: str, session_id: str) -> Agent:
    """Tạo một Agent mới với tools được inject context cho project."""
    tools = _build_graph_tools(project_id, jwt_token, session_id)
    return Agent(
        name="memora_assistant",
        model=LiteLlm(
            model=f"openai/{settings.OPENAI_MODEL}",
            api_base=settings.OPENAI_BASE_URL,
            api_key=settings.OPENAI_API_KEY,
        ),
        instruction=(
            "You are a helpful AI assistant for the Memora knowledge management system. "
            "You have tools to query the project's knowledge graph AND search the full text of "
            "uploaded documents (via semantic + hybrid search).\n\n"
            "Decision rules:\n"
            "- If the user asks about content, a quote, or detail from a file/document/report/paper, "
            "or anything that may live in an uploaded file → ALWAYS call llm_search_hybrid first "
            "(combines graph + document chunks).\n"
            "- For pure graph questions (concepts, relations) use llm_query_graph or llm_traverse_graph.\n"
            "- Cite the source by referencing the chunk text you retrieved.\n"
            "- If no tool returns useful info, say so — do not invent.\n"
            "Return the answer in plain text; the system will attach citation metadata."
        ),
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


async def _sync_redis_history_to_session(session_id: str, session: Session):
    """Sync short-term history from Redis to ADK session."""
    redis_messages = session_manager.get_messages(session_id)
    if session.events or not redis_messages:
        return
    logger.info(f"Syncing {len(redis_messages)} history messages from Redis to session {session_id}")
    for msg in redis_messages:
        role = msg["role"]
        content = msg["content"]
        gemini_role = "user" if role == "user" else "model"
        # Crucial fix: Must append event through session_service.append_event()
        # to ensure it's written to storage and not lost on copies.
        await session_service.append_event(
            session=session,
            event=Event(
                content=types.Content(
                    parts=[types.Part(text=content)], role=gemini_role
                ),
                author=gemini_role,
            )
        )


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
        await _sync_redis_history_to_session(session_id, session)

        _clear_metadata(project_id, session_id)
        agent = _create_agent(project_id, jwt_token, session_id)
        runner = InMemoryRunner(agent=agent, app_name=app_name)
        runner.auto_create_session = True

        content = types.Content(parts=[types.Part(text=message)], role="user")

        session_manager.append_message(session_id, "user", message)

        final_response = ""
        async for event in runner.run_async(
            user_id="default",
            session_id=session_id,
            new_message=content,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final_response = event.content.parts[0].text or ""

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
        await _sync_redis_history_to_session(session_id, session)

        _clear_metadata(project_id, session_id)
        agent = _create_agent(project_id, jwt_token, session_id)
        runner = InMemoryRunner(agent=agent, app_name=app_name)
        runner.auto_create_session = True

        content = types.Content(parts=[types.Part(text=message)], role="user")

        session_manager.append_message(session_id, "user", message)

        accumulated = ""
        event_count = 0
        async for event in runner.run_async(
            user_id="default",
            session_id=session_id,
            new_message=content,
        ):
            event_count += 1
            if event.content:
                parts = event.content.parts
                if parts:
                    text_chunk = parts[0].text or ""
                    accumulated += text_chunk
                    yield text_chunk

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

