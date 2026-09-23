import unittest
from unittest.mock import AsyncMock, patch

from app.clients.graph_client import GraphClient
from app.clients.nestjs_client import NestJSClient
from app.services.concept_extractor import aextract_concepts
from app.services.document_processor import extract_markdown


class TestBatchGraphAndExtraction(unittest.IsolatedAsyncioTestCase):
    async def test_batch_write_graph_success(self):
        mock_client = AsyncMock(spec=NestJSClient)
        mock_client.internal_post.return_value = {
            "createdNodes": 2,
            "createdEdges": 1,
            "nodeIdMap": {"node a": "uuid-1", "node b": "uuid-2"},
        }
        mock_client.post.return_value = {
            "createdNodes": 2,
            "createdEdges": 1,
            "nodeIdMap": {"node a": "uuid-1", "node b": "uuid-2"},
        }
        graph_client = GraphClient(mock_client)

        graph_data = {
            "nodes": [
                {"title": "Node A", "description": "Desc A"},
                {"title": "Node B", "description": "Desc B"},
            ],
            "edges": [
                {"source": "Node A", "target": "Node B", "type": "RELATES_TO"},
            ],
        }

        res = await graph_client.batch_write_graph("proj-1", "jwt-token", graph_data)
        self.assertEqual(res["createdNodes"], 2)
        self.assertEqual(res["createdEdges"], 1)
        mock_client.internal_post.assert_awaited_once()

    async def test_batch_write_graph_fallback_on_error(self):
        mock_client = AsyncMock(spec=NestJSClient)
        mock_client.internal_post.side_effect = Exception("500 Internal Server Error")
        mock_client.post.side_effect = Exception("500 Internal Server Error")
        graph_client = GraphClient(mock_client)

        with patch.object(graph_client, "write_graph", new_callable=AsyncMock) as mock_legacy_write:
            graph_data = {
                "nodes": [{"title": "Node A"}],
                "edges": [],
            }
            res = await graph_client.batch_write_graph("proj-1", "jwt-token", graph_data)
            mock_legacy_write.assert_awaited_once()
            self.assertEqual(res["createdNodes"], 1)

    @patch("app.services.concept_extractor.get_chat_model")
    async def test_aextract_concepts_parses_json(self, mock_get_chat_model):
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value.content = (
            '{"nodes": [{"title": "Graph Theory", "description": "Study of graphs"}], "edges": []}'
        )
        mock_get_chat_model.return_value = mock_llm

        data = await aextract_concepts("Sample content about Graph Theory.")
        self.assertIn("nodes", data)
        self.assertEqual(data["nodes"][0]["title"], "Graph Theory")


if __name__ == "__main__":
    unittest.main()
