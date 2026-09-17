"""Test FastAPI endpoints for health, search, and document-reader."""
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.file_storage import save_document
from tests.test_file_storage import MockBackendStorage


class TestRoutes(unittest.TestCase):
    def setUp(self):
        self._backend = patch("app.services.file_storage._request", side_effect=MockBackendStorage())
        self._backend.start()
        self._temp_dir = tempfile.TemporaryDirectory()
        self._orig_storage = settings.STORAGE_BASE_DIR
        settings.STORAGE_BASE_DIR = self._temp_dir.name
        self.client = TestClient(app)

    def tearDown(self):
        self._backend.stop()
        settings.STORAGE_BASE_DIR = self._orig_storage
        self._temp_dir.cleanup()

    def test_health_check(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "healthy", "service": "memora-ai"})

    @patch("app.clients.graph_client.GraphClient.get_nodes", new_callable=AsyncMock)
    def test_search_endpoint(self, mock_get_nodes):
        project_id = "test_search_proj"
        file_id = "file_search_1"
        save_document(
            project_id,
            file_id,
            "Line 1: Artificial Intelligence overview\nLine 2: Deep Learning fundamentals",
            metadata={"originalName": "ai_doc.md"},
        )
        mock_get_nodes.return_value = [
            {"id": "node_1", "label": "Artificial Intelligence", "properties": {}},
            {"id": "node_2", "label": "Database", "properties": {}},
        ]

        response = self.client.post(
            "/api/search",
            json={
                "q": "Artificial Intelligence",
                "project_id": project_id,
                "jwt_token": "mock_jwt",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("matches", data)
        self.assertEqual(len(data["matches"]), 1)
        self.assertEqual(data["matches"][0]["file_id"], file_id)
        self.assertIn("nodes", data)
        self.assertEqual(len(data["nodes"]), 1)
        self.assertEqual(data["nodes"][0]["nodeId"], "node_1")
        self.assertEqual(data["nodes"][0]["nodeName"], "Artificial Intelligence")

    def test_search_empty_query_fails(self):
        response = self.client.post(
            "/api/search",
            json={
                "q": "   ",
                "project_id": "proj",
                "jwt_token": "mock_jwt",
            },
        )
        self.assertEqual(response.status_code, 400)

    @patch("app.api.routes.document_reader.get_chat_model")
    def test_document_reader_summary(self, mock_get_chat_model):
        mock_llm = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.content = "Summary of the document."
        mock_llm.ainvoke.return_value = mock_resp
        mock_get_chat_model.return_value = mock_llm

        project_id = "test_reader_proj"
        file_id = "file_reader_1"
        save_document(
            project_id,
            file_id,
            "Document text content for summary testing.",
            metadata={"originalName": "test.txt"},
        )

        response = self.client.post(
            "/api/document-reader/summary",
            json={
                "file_id": file_id,
                "project_id": project_id,
                "jwt_token": "mock_jwt",
                "type": "short",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("summary", data)
        self.assertEqual(data["summary"], "Summary of the document.")
        self.assertEqual(data["type"], "short")


if __name__ == "__main__":
    unittest.main()
