"""Unit tests for AI chat cluster management tools."""
import unittest
from unittest.mock import AsyncMock, patch

from app.clients.graph_client import GraphClient
from app.services.chat.tool_builder import build_graph_tools


class TestClusterTools(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_client = AsyncMock(spec=GraphClient)
        self.project_id = "test-proj"
        self.jwt_token = "test-jwt"
        self.session_id = "test-sess"

        tools = build_graph_tools(
            self.project_id,
            self.jwt_token,
            self.session_id,
            graph_client=self.mock_client,
        )
        self.tools_by_name = {t.__name__: t for t in tools}

    def test_tools_registered(self):
        for name in [
            "llm_get_clusters",
            "llm_create_cluster",
            "llm_add_node_to_cluster",
            "llm_remove_node_from_cluster",
        ]:
            self.assertIn(name, self.tools_by_name)

    async def test_llm_get_clusters(self):
        tool = self.tools_by_name["llm_get_clusters"]
        self.mock_client.get_clusters.return_value = {
            "clusters": [{"clusterId": "c1", "name": "AI", "nodeIds": ["n1"]}],
            "totalClusters": 1,
        }
        res = await tool()
        self.assertEqual(res["totalClusters"], 1)
        self.mock_client.get_clusters.assert_called_once_with(
            self.project_id, self.jwt_token
        )

    async def test_llm_create_cluster_resolves_node_name(self):
        tool = self.tools_by_name["llm_create_cluster"]
        self.mock_client.get_nodes.return_value = [
            {"nodeId": "uuid-1", "nodeName": "Quantum Computing"}
        ]
        self.mock_client.create_cluster.return_value = {
            "clusterId": "c1",
            "name": "Physics",
            "nodeIds": ["uuid-1"],
        }

        with patch("app.services.chat.tool_builder.record_mutation") as mock_mut:
            res = await tool(name="Physics", node_ids=["Quantum Computing"], color="#EC4899")
            self.assertEqual(res["clusterId"], "c1")
            self.mock_client.create_cluster.assert_called_once_with(
                self.project_id,
                self.jwt_token,
                {"name": "Physics", "color": "#EC4899", "nodeIds": ["uuid-1"]},
            )
            mock_mut.assert_called_once_with(
                self.project_id, self.session_id, "cluster_created", nodes=["uuid-1"], edges=()
            )

    async def test_llm_add_node_to_cluster_resolves_names(self):
        tool = self.tools_by_name["llm_add_node_to_cluster"]
        self.mock_client.get_clusters.return_value = {
            "clusters": [{"clusterId": "cluster_abc", "name": "Machine Learning"}]
        }
        self.mock_client.get_nodes.return_value = [
            {"nodeId": "uuid-node-99", "nodeName": "Neural Networks"}
        ]
        self.mock_client.add_node_to_cluster.return_value = {
            "clusterId": "cluster_abc",
            "nodeIds": ["uuid-node-99"],
        }

        with patch("app.services.chat.tool_builder.record_mutation") as mock_mut:
            res = await tool(cluster_id="Machine Learning", node_id="Neural Networks")
            self.assertEqual(res["clusterId"], "cluster_abc")
            self.mock_client.add_node_to_cluster.assert_called_once_with(
                self.project_id, self.jwt_token, "cluster_abc", "uuid-node-99"
            )
            mock_mut.assert_called_once_with(
                self.project_id, self.session_id, "cluster_updated", nodes=["uuid-node-99"], edges=()
            )

    async def test_llm_remove_node_from_cluster_resolves_names(self):
        tool = self.tools_by_name["llm_remove_node_from_cluster"]
        self.mock_client.get_clusters.return_value = {
            "clusters": [{"clusterId": "cluster_abc", "name": "Machine Learning"}]
        }
        self.mock_client.get_nodes.return_value = [
            {"nodeId": "uuid-node-99", "nodeName": "Neural Networks"}
        ]
        self.mock_client.remove_node_from_cluster.return_value = {
            "success": True,
            "clusterId": "cluster_abc",
            "nodeId": "uuid-node-99",
        }

        with patch("app.services.chat.tool_builder.record_mutation") as mock_mut:
            res = await tool(cluster_id="Machine Learning", node_id="Neural Networks")
            self.assertTrue(res["success"])
            self.mock_client.remove_node_from_cluster.assert_called_once_with(
                self.project_id, self.jwt_token, "cluster_abc", "uuid-node-99"
            )
            mock_mut.assert_called_once_with(
                self.project_id, self.session_id, "cluster_updated", nodes=["uuid-node-99"], edges=()
            )


if __name__ == "__main__":
    unittest.main()
