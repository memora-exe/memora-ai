"""Test ingestion pipeline saving to file_storage without vector_store/embedding."""
import unittest
from unittest.mock import AsyncMock, patch

from app.services.ingestion.pipeline import process_file_pipeline


class TestIngestionPipeline(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.ingestion.pipeline._graph_client.download_file", new_callable=AsyncMock)
    @patch("app.services.ingestion.pipeline._graph_client.batch_write_graph", new_callable=AsyncMock)
    @patch("app.services.ingestion.pipeline.extract_markdown")
    @patch("app.services.ingestion.pipeline.aextract_concepts", new_callable=AsyncMock)
    @patch("app.services.ingestion.pipeline.asave_document", new_callable=AsyncMock)
    @patch("app.services.ingestion.pipeline.is_file_active", new_callable=AsyncMock)
    async def test_process_file_pipeline_success(
        self,
        mock_is_active,
        mock_asave_document,
        mock_aextract_concepts,
        mock_extract_markdown,
        mock_batch_write_graph,
        mock_download_file,
    ):
        mock_download_file.return_value = b"sample file bytes"
        mock_extract_markdown.return_value = "Paragraph 1\nParagraph 2 content"
        mock_is_active.return_value = True
        mock_aextract_concepts.return_value = {"nodes": [{"title": "ConceptA"}], "edges": []}
        mock_batch_write_graph.return_value = {"createdNodes": 1, "createdEdges": 0}

        project_id = "test_proj_pipeline"
        file_id = "test_file_123"
        key = "uploads/report.pdf"
        jwt_token = "mock_jwt"

        await process_file_pipeline(file_id, key, project_id, jwt_token)

        # Verify asave_document called with extracted text
        mock_asave_document.assert_awaited_once_with(
            project_id,
            file_id,
            "Paragraph 1\nParagraph 2 content",
            {
                "originalName": "report.pdf",
                "projectId": project_id,
            },
        )

        # Verify concepts were extracted and batch-written to graph
        mock_aextract_concepts.assert_awaited_once_with("Paragraph 1\nParagraph 2 content")
        mock_batch_write_graph.assert_awaited_once_with(
            project_id, jwt_token, {"nodes": [{"title": "ConceptA"}], "edges": []}
        )

    def test_clean_extracted_text_sanitizes_binary(self):
        from app.services.document_processor import clean_extracted_text
        # Null bytes and control characters stripped
        raw_with_nulls = "Hello\x00 World\x08!\x0b\x0c"
        self.assertEqual(clean_extracted_text(raw_with_nulls), "Hello World!")

        # Raw PDF header detected and avoided
        raw_pdf = "%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>"
        self.assertTrue(clean_extracted_text(raw_pdf).startswith("[Binary PDF stream"))


if __name__ == "__main__":
    unittest.main()
