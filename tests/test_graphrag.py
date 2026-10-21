"""Unit tests for GraphRAG context retriever and Markdown serialization."""
import unittest
from unittest.mock import AsyncMock, patch

from app.services.search.graphrag_retriever import (
    GraphRagRetriever,
    serialize_graphrag_markdown,
)


class TestGraphRagRetriever(unittest.IsolatedAsyncioTestCase):
    def test_serialize_graphrag_markdown_format(self):
        seeds = [
            {"nodeId": "n1", "nodeName": "Auth Service", "note": "Handles authentication and JWT tokens."}
        ]
        subgraph_nodes = [
            {"nodeId": "n1", "nodeName": "Auth Service"},
            {"nodeId": "n2", "nodeName": "Database Pool", "note": "PostgreSQL pool"},
            {"nodeId": "n3", "nodeName": "User Entity"},
        ]
        subgraph_edges = [
            {
                "edgeId": "e1",
                "sourceNodeId": "n1",
                "targetNodeId": "n2",
                "predicate": "DEPENDS_ON",
            },
            {
                "edgeId": "e2",
                "sourceNodeId": "n2",
                "targetNodeId": "n3",
                "properties": {"isMention": True},
            },
        ]

        md = serialize_graphrag_markdown(seeds, subgraph_nodes, subgraph_edges, query="Auth")

        self.assertIn("### Knowledge Graph Context", md)
        self.assertIn("#### Matched Seed Entities:", md)
        self.assertIn("- **Auth Service** (ID: n1): Handles authentication and JWT tokens.", md)
        self.assertIn("#### Connected Subgraph (1-2 Hops):", md)
        self.assertIn('- (Auth Service) -[:RELATES_TO {predicate: "DEPENDS_ON"}]-> (Database Pool)', md)
        self.assertIn("- (Database Pool) -[:RELATES_TO {isMention: true}]-> (User Entity)", md)

    def test_serialize_graphrag_markdown_empty(self):
        md = serialize_graphrag_markdown([], [], [])
        self.assertIn("### Knowledge Graph Context", md)
        self.assertIn("#### Matched Seed Entities:", md)
        self.assertIn("No direct seed entity matches found", md)
        self.assertIn("No connected relationships found within 1-2 hops", md)

    async def test_retrieve_context_from_backend(self):
        mock_nestjs = AsyncMock()
        mock_nestjs.get.return_value = {
            "seeds": [{"nodeId": "n1", "nodeName": "Auth Service"}],
            "subgraphNodes": [{"nodeId": "n1", "nodeName": "Auth Service"}],
            "subgraphEdges": [],
            "serializedMarkdown": "### Knowledge Graph Context\n#### Matched Seed Entities:\n- **Auth Service**",
        }
        retriever = GraphRagRetriever(nestjs_client=mock_nestjs)
        res = await retriever.retrieve_context("proj-1", "Auth", "jwt-token")

        self.assertIn("serializedMarkdown", res)
        self.assertEqual(len(res["seeds"]), 1)
        mock_nestjs.get.assert_awaited_once_with(
            "/projects/proj-1/search/graphrag",
            "jwt-token",
            params={"q": "Auth", "maxHops": 2, "maxSeeds": 5},
        )

    async def test_retrieve_context_fallback_local(self):
        mock_nestjs = AsyncMock()
        mock_nestjs.get.side_effect = Exception("404 Not Found")

        mock_graph = AsyncMock()
        mock_graph.get_nodes.return_value = [
            {"nodeId": "n1", "nodeName": "Authentication Service", "note": "Token issuer"},
            {"nodeId": "n2", "nodeName": "PostgreSQL", "note": "Database"},
        ]
        mock_graph.traverse_graph.return_value = {
            "nodes": [
                {"nodeId": "n1", "nodeName": "Authentication Service"},
                {"nodeId": "n2", "nodeName": "PostgreSQL"},
            ],
            "edges": [
                {"edgeId": "e1", "sourceNodeId": "n1", "targetNodeId": "n2", "predicate": "USES"}
            ],
        }

        retriever = GraphRagRetriever(nestjs_client=mock_nestjs, graph_client=mock_graph)
        res = await retriever.retrieve_context("proj-1", "Auth Service", "jwt-token")

        self.assertIn("serializedMarkdown", res)
        self.assertIn("Authentication Service", res["serializedMarkdown"])
        self.assertIn('- (Authentication Service) -[:RELATES_TO {predicate: "USES"}]-> (PostgreSQL)', res["serializedMarkdown"])

    async def test_retrieve_context_empty_query(self):
        retriever = GraphRagRetriever()
        res = await retriever.retrieve_context("proj-1", "")
        self.assertEqual(res["seeds"], [])
        self.assertIn("### Knowledge Graph Context", res["serializedMarkdown"])

    async def test_llm_graphrag_search_tool(self):
        from app.clients.graph_client import GraphClient
        from app.services.chat.tool_builder import build_graph_tools

        mock_gc = AsyncMock(spec=GraphClient)
        mock_gc.get_nodes.return_value = [
            {"nodeId": "n1", "nodeName": "Auth Service", "note": "Auth note"}
        ]
        mock_gc.traverse_graph.return_value = {
            "nodes": [{"nodeId": "n1", "nodeName": "Auth Service"}],
            "edges": [],
        }

        tools = build_graph_tools(
            project_id="proj-1",
            jwt_token="jwt-1",
            session_id="sess-1",
            graph_client=mock_gc,
        )
        tool_map = {t.__name__: t for t in tools}
        self.assertIn("llm_graphrag_search", tool_map)

        graphrag_tool = tool_map["llm_graphrag_search"]
        result = await graphrag_tool(query="Auth Service")
        self.assertIn("context", result)
        self.assertIn("### Knowledge Graph Context", result["context"])
        self.assertEqual(result["seed_count"], 1)


if __name__ == "__main__":
    unittest.main()
