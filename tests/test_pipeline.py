"""Test ingestion pipeline saving to file_storage without vector_store/embedding."""
import unittest
from unittest.mock import AsyncMock, patch

from app.services.file_storage import read_full_text
from app.services.ingestion.pipeline import process_file_pipeline
from tests.test_file_storage import MockBackendStorage


class TestIngestionPipeline(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_backend = MockBackendStorage()
        self.patcher = patch("app.services.file_storage._request", side_effect=self.mock_backend)
        self.patcher.start()

    async def asyncTearDown(self):
        self.patcher.stop()

    @patch("app.services.ingestion.pipeline._graph_client.download_file", new_callable=AsyncMock)
    @patch("app.services.ingestion.pipeline._graph_client.write_graph", new_callable=AsyncMock)
    @patch("app.services.ingestion.pipeline.process_document")
    @patch("app.services.ingestion.pipeline.extract_concepts")
    @patch("app.services.ingestion.pipeline.is_file_active", new_callable=AsyncMock)
    async def test_process_file_pipeline_success(
        self,
        mock_is_active,
        mock_extract_concepts,
        mock_process_document,
        mock_write_graph,
        mock_download_file,
    ):
        mock_download_file.return_value = b"sample file bytes"
        mock_process_document.return_value = ["Paragraph 1", "Paragraph 2 content"]
        mock_is_active.return_value = True
        mock_extract_concepts.return_value = [{"name": "ConceptA"}]

        project_id = "test_proj_pipeline"
        file_id = "test_file_123"
        key = "uploads/report.pdf"
        jwt_token = "mock_jwt"

        await process_file_pipeline(file_id, key, project_id, jwt_token)

        # Verify file written to backend via file_storage
        saved_text = read_full_text(project_id, file_id)
        self.assertEqual(saved_text, "Paragraph 1\nParagraph 2 content")

        # Verify concepts were extracted and written to graph
        mock_extract_concepts.assert_called_once()
        mock_write_graph.assert_called_once_with(project_id, jwt_token, [{"name": "ConceptA"}])


if __name__ == "__main__":
    unittest.main()
