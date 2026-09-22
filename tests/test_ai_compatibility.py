"""Tests for AI compatibility: node shape fallback, mention edges, prompt formatting, mutation tracking."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.api.routes.search import ai_search
from app.services.search.focal_area import compute_focal_area, project_to_search_shape
from app.services.chat.tool_builder import build_graph_tools
from app.services.chat.metadata_tracker import (
    clear_metadata,
    get_metadata,
    record_mutation,
    build_citation_metadata,
)
from app.schemas.search import SearchRequest


def test_node_shape_fallback_in_search_projection():
    """Verify project_to_search_shape handles NestJS NodeRes (nodeId, nodeName) without id or label or nodeType."""
    nodes = [
        {"nodeId": "uuid-1", "nodeName": "Quantum Computing", "similarity_score": 0.95},
        {"id": "uuid-2", "label": "Machine Learning", "type": "Topic"},
        {"elementId": "uuid-3", "name": "Deep Learning"},
    ]
    res = project_to_search_shape(nodes)
    assert len(res["nodes"]) == 3
    assert res["nodes"][0] == {"nodeId": "uuid-1", "nodeName": "Quantum Computing", "similarityScore": 0.95}
    assert res["nodes"][1] == {"nodeId": "uuid-2", "nodeName": "Machine Learning", "similarityScore": None}
    assert res["nodes"][2] == {"nodeId": "uuid-3", "nodeName": "Deep Learning", "similarityScore": None}


def test_focal_area_with_nestjs_shape():
    """Verify compute_focal_area calculates bounding box on nodes with x/y or layout."""
    nodes = [
        {"nodeId": "uuid-1", "nodeName": "Node A", "x": 100, "y": 200},
        {"nodeId": "uuid-2", "nodeName": "Node B", "x": 300, "y": 400},
    ]
    focal = compute_focal_area(nodes)
    assert focal["cx"] == 200.0
    assert focal["cy"] == 300.0
    assert focal["zoom"] > 0


def test_search_route_node_name_fallback():
    """Verify ai_search matches on nodeName from backend NodeRes."""
    import asyncio
    mock_client = MagicMock()
    mock_client.get_nodes = AsyncMock(return_value=[
        {"nodeId": "uuid-1", "nodeName": "Neural Networks", "note": "Concepts"},
        {"nodeId": "uuid-2", "nodeName": "Relational Databases", "note": "SQL"},
    ])

    req = SearchRequest(q="neural", project_id="proj-1", jwt_token="mock-jwt")
    result = asyncio.run(ai_search(req, graph_client=mock_client))

    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["nodeId"] == "uuid-1"
    assert result["nodes"][0]["nodeName"] == "Neural Networks"


@pytest.mark.anyio
async def test_graph_tools_mention_edge_and_mutation():
    """Verify tool closures handle mention edges and record mutations."""
    project_id = "proj-test"
    session_id = "sess-test"
    jwt_token = "jwt-test"
    clear_metadata(project_id, session_id)

    mock_client = MagicMock()
    mock_client.get_nodes = AsyncMock(return_value=[
        {"nodeId": "node-1", "nodeName": "Node 1"},
        {"nodeId": "node-2", "nodeName": "Node 2"},
    ])
    mock_client.find_path = AsyncMock(return_value={
        "nodes": [
            {"nodeId": "node-1", "nodeName": "Node 1", "note": "See [[Node 2]]"},
            {"nodeId": "node-2", "nodeName": "Node 2", "note": ""},
        ],
        "edges": [
            {
                "edgeId": "edge-m1",
                "sourceNodeId": "node-1",
                "targetNodeId": "node-2",
                "edgeTypeId": None,
                "properties": {"isMention": True, "sourceText": "wikilink"},
            }
        ],
        "bridgeNodes": [],
    })
    mock_client.create_node = AsyncMock(return_value={"nodeId": "node-new-1", "nodeName": "Created Concept"})
    mock_client.create_edge = AsyncMock(return_value={"edgeId": "edge-new-1"})

    tools_list = build_graph_tools(project_id, jwt_token, session_id, graph_client=mock_client)
    tools = {t.__name__: t for t in tools_list}

    # 1. Test find_path recognizes mention edge
    find_path_res = await tools["llm_find_path"]("node-1", "node-2")
    assert find_path_res["found"] is True
    meta = get_metadata(project_id, session_id)
    assert "reasoningPath" in meta
    assert len(meta["reasoningPath"]) == 1
    assert meta["reasoningPath"][0]["relation"] == "RELATES_TO (wikilink mention)"

    # 2. Test create_node mutations
    create_node_res = await tools["llm_create_node"](node_name="Created Concept", note="Linked to [[Node 2]]")
    assert create_node_res["nodeId"] == "node-new-1"
    mut_meta = get_metadata(project_id, session_id)
    assert "node-new-1" in mut_meta["mutatedEntities"]["created"]["nodes"]

    # 3. Test create_edge mutations with edge_type_id=None
    create_edge_res = await tools["llm_create_edge"](source_node_id="node-1", target_node_id="node-2")
    assert create_edge_res["edgeId"] == "edge-new-1"
    mut_meta = get_metadata(project_id, session_id)
    assert "edge-new-1" in mut_meta["mutatedEntities"]["created"]["edges"]

    # 4. Citation metadata packaging
    meta_state = get_metadata(project_id, session_id)
    citation_meta = build_citation_metadata(meta_state)
    assert "mutatedEntities" in citation_meta
    assert "node-new-1" in citation_meta["mutatedEntities"]["created"]["nodes"]
    assert "edge-new-1" in citation_meta["mutatedEntities"]["created"]["edges"]
    clear_metadata(project_id, session_id)


def test_prompt_content_includes_wikilink_and_no_types():
    """Verify chat_agent.md prompt teaches [[NodeName]] and explains no nodeType/edgeType required."""
    from pathlib import Path
    prompt_path = Path(__file__).parent.parent / "app" / "prompts" / "chat_agent.md"
    content = prompt_path.read_text(encoding="utf-8")

    assert "[[NodeName]]" in content
    assert "isMention: true" in content
    assert "Bi-directional Linking" in content
    assert "No NodeType or EdgeType Required" in content
