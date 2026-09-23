"""Unit test for community detection and multi-cluster node membership."""
import unittest
from unittest.mock import AsyncMock

from app.services.cluster_engine import detect_communities


class TestClusters(unittest.IsolatedAsyncioTestCase):
    async def test_multi_cluster_membership(self):
        client = AsyncMock()
        client.get_nodes.return_value = [
            {"nodeId": "A1", "nodeName": "Node A1"},
            {"nodeId": "A2", "nodeName": "Node A2"},
            {"nodeId": "B1", "nodeName": "Node B1"},
            {"nodeId": "B2", "nodeName": "Node B2"},
            {"nodeId": "Bridge", "nodeName": "Bridge Node"},
        ]
        client.get_edges.return_value = [
            {"sourceNodeId": "A1", "targetNodeId": "A2"},
            {"sourceNodeId": "A1", "targetNodeId": "Bridge"},
            {"sourceNodeId": "B1", "targetNodeId": "B2"},
            {"sourceNodeId": "B1", "targetNodeId": "Bridge"},
        ]

        result = await detect_communities("proj-test", "token", client)
        self.assertGreaterEqual(result["totalClusters"], 2)

        clusters = result["clusters"]
        bridge_clusters = [c for c in clusters if "Bridge" in c["nodeIds"]]
        # Bridge node should belong to multiple clusters
        self.assertGreaterEqual(len(bridge_clusters), 2)


if __name__ == "__main__":
    unittest.main()
