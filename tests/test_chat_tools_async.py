"""Tests for native async graph tools and event loop safety in Chat Agent."""
import inspect
from unittest.mock import AsyncMock, MagicMock
import pytest
from google.adk.tools import FunctionTool

from app.clients.graph_client import GraphClient
from app.clients.nestjs_client import NestJSClient
from app.services.chat.tool_builder import build_graph_tools
from app.services.chat.metadata_tracker import clear_metadata, get_metadata


ASYNC_TOOL_NAMES = {
    "llm_get_all_nodes",
    "llm_get_all_edges",
    "llm_query_graph",
    "llm_traverse_graph",
    "llm_find_path",
    "llm_generate_flashcards",
    "llm_create_node",
    "llm_update_node",
    "llm_update_node_note",
    "llm_delete_node",
    "llm_create_edge",
    "llm_update_edge",
    "llm_delete_edge",
    "llm_list_node_types",
    "llm_list_files",
    "llm_read_file",
}

SYNC_TOOL_NAMES = {
    "llm_glob_files",
    "llm_grep_search",
    "llm_read_file_content",
    "llm_highlight",
}


def test_tool_function_types():
    """Verify 16 graph tools are native coroutines and 4 local tools are sync functions."""
    mock_client = MagicMock(spec=GraphClient)
    tools_list = build_graph_tools(
        project_id="proj-1",
        jwt_token="mock-jwt",
        session_id="sess-1",
        graph_client=mock_client,
    )
    tools = {t.__name__: t for t in tools_list}

    assert len(tools) == 20
    for name in ASYNC_TOOL_NAMES:
        assert name in tools, f"Missing async tool {name}"
        assert inspect.iscoroutinefunction(tools[name]), f"Tool {name} should be async def"

    for name in SYNC_TOOL_NAMES:
        assert name in tools, f"Missing sync tool {name}"
        assert not inspect.iscoroutinefunction(tools[name]), f"Tool {name} should be sync def"


@pytest.mark.anyio
async def test_adk_function_tool_execution():
    """Verify Google ADK FunctionTool can execute both async and sync tools in the running loop."""
    mock_client = MagicMock(spec=GraphClient)
    mock_client.create_node = AsyncMock(return_value={"nodeId": "node-101", "nodeName": "AsyncConcept"})

    clear_metadata("proj-1", "sess-1")
    tools_list = build_graph_tools(
        project_id="proj-1",
        jwt_token="mock-jwt",
        session_id="sess-1",
        graph_client=mock_client,
    )
    tools = {t.__name__: t for t in tools_list}

    # 1. Async tool wrapped in ADK FunctionTool
    async_tool = FunctionTool(tools["llm_create_node"])
    res_async = await async_tool.run_async(
        args={"node_name": "AsyncConcept", "note": "Testing ADK async support"},
        tool_context=MagicMock(),
    )
    assert res_async["nodeId"] == "node-101"

    # 2. Sync tool wrapped in ADK FunctionTool
    sync_tool = FunctionTool(tools["llm_highlight"])
    res_sync = await sync_tool.run_async(
        args={"ids": ["node-101"], "default_color": "#00E676"},
        tool_context=MagicMock(),
    )
    assert res_sync["highlighted_count"] == 1
    clear_metadata("proj-1", "sess-1")


@pytest.mark.anyio
async def test_sequential_write_tools_no_closed_loop():
    """Verify sequential write tool calls do not trigger 'Event loop is closed' errors."""
    mock_client = MagicMock(spec=GraphClient)
    mock_client.create_node = AsyncMock(side_effect=[
        {"nodeId": "node-1", "nodeName": "First"},
        {"nodeId": "node-2", "nodeName": "Second"},
    ])
    mock_client.create_edge = AsyncMock(return_value={"edgeId": "edge-1"})
    mock_client.update_node = AsyncMock(return_value={"nodeId": "node-1", "note": "Updated"})
    mock_client.delete_edge = AsyncMock(return_value={"edgeId": "edge-1"})

    clear_metadata("proj-seq", "sess-seq")
    tools_list = build_graph_tools(
        project_id="proj-seq",
        jwt_token="mock-jwt",
        session_id="sess-seq",
        graph_client=mock_client,
    )
    tools = {t.__name__: t for t in tools_list}

    # Sequence of multiple tool calls in same event loop
    n1 = await tools["llm_create_node"](node_name="First")
    n2 = await tools["llm_create_node"](node_name="Second")
    e1 = await tools["llm_create_edge"](source_node_id=n1["nodeId"], target_node_id=n2["nodeId"])
    u1 = await tools["llm_update_node"](node_id=n1["nodeId"], note="Updated")
    d1 = await tools["llm_delete_edge"](edge_id=e1["edgeId"])

    assert n1["nodeId"] == "node-1"
    assert n2["nodeId"] == "node-2"
    assert e1["edgeId"] == "edge-1"
    assert u1["note"] == "Updated"

    meta = get_metadata("proj-seq", "sess-seq")
    assert "node-1" in meta["mutatedEntities"]["created"]["nodes"]
    assert "node-2" in meta["mutatedEntities"]["created"]["nodes"]
    assert "edge-1" in meta["mutatedEntities"]["created"]["edges"]
    assert "node-1" in meta["mutatedEntities"]["updated"]["nodes"]
    assert "edge-1" in meta["mutatedEntities"]["deleted"]["edges"]
    clear_metadata("proj-seq", "sess-seq")


@pytest.mark.anyio
async def test_nestjs_client_lazy_reconnection():
    """Verify NestJSClient automatically recreates http_client if closed."""
    client = NestJSClient("http://localhost:3010")

    # Initial client access
    http_c1 = client.http_client
    assert http_c1 is not None
    assert not http_c1.is_closed

    # Close client
    await client.close()
    assert client._http_client is None

    # Next access should lazily recreate new AsyncClient
    http_c2 = client.http_client
    assert http_c2 is not None
    assert not http_c2.is_closed
    assert http_c2 is not http_c1

    # Cleanup
    await client.close()
    assert client._http_client is None
