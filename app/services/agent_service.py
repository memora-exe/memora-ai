import asyncio
import os
from google.genai import types
from google.adk import Agent
from google.adk.runners import InMemoryRunner
from google.adk.sessions import Session, InMemorySessionService
from app.core.config import settings
from app.services.graph_tools import (
    get_project_nodes,
    get_project_edges,
    query_project_graph,
    traverse_project_graph,
)

# Đảm bảo API key được set cho Gemini model
if settings.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = settings.GOOGLE_API_KEY

app_name = "memora"
session_service = InMemorySessionService()


def _build_graph_tools(project_id: str, jwt_token: str) -> list:
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

    return [llm_get_all_nodes, llm_get_all_edges, llm_query_graph, llm_traverse_graph]


def _create_agent(project_id: str, jwt_token: str) -> Agent:
    """Tạo một Agent mới với tools được inject context cho project."""
    tools = _build_graph_tools(project_id, jwt_token)
    return Agent(
        name="memora_assistant",
        model="gemini-2.5-flash",
        instruction=(
            "You are a helpful AI assistant for the Memora knowledge management system. "
            "You have access to the current project's knowledge graph. "
            "Use the provided tools to query nodes, edges, and relationships when needed to answer user questions. "
            "Always answer accurately and concisely. "
            "If you cannot find relevant information in the graph, say so clearly."
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


async def process_chat_message(
    message: str, session_id: str, project_id: str, jwt_token: str
) -> str:
    """
    Process a chat message using the ADK Agent (full response).
    Agent được tạo động với tools đã inject project_id và jwt_token.
    """
    await _get_or_create_session(session_id)

    agent = _create_agent(project_id, jwt_token)
    runner = InMemoryRunner(agent=agent, app_name=app_name)
    runner.auto_create_session = True

    content = types.Content(parts=[types.Part(text=message)], role="user")

    final_response = ""
    async for event in runner.run_async(
        user_id="default",
        session_id=session_id,
        new_message=content,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_response = event.content.parts[0].text or ""

    return final_response if final_response else "Sorry, I could not process your request."


async def process_chat_message_stream(
    message: str, session_id: str, project_id: str, jwt_token: str
):
    """
    Process a chat message and yield chunks for SSE (Server-Sent Events).
    Agent được tạo động với tools đã inject project_id và jwt_token.
    """
    await _get_or_create_session(session_id)

    agent = _create_agent(project_id, jwt_token)
    runner = InMemoryRunner(agent=agent, app_name=app_name)
    runner.auto_create_session = True

    content = types.Content(parts=[types.Part(text=message)], role="user")

    async for event in runner.run_async(
        user_id="default",
        session_id=session_id,
        new_message=content,
    ):
        if event.content and event.is_final_response():
            yield event.content
        elif event.content:
            yield event.content
