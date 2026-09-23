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

    async def test_download_file_uses_http_client_property(self):
        """Ensure download_file uses .http_client property instead of uninitialized ._http_client."""
        from app.clients.graph_client import GraphClient
        from app.clients.nestjs_client import NestJSClient

        client = NestJSClient("http://localhost:3010")
        assert client._http_client is None  # initially None

        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.content = b"downloaded bytes"
        mock_resp.raise_for_status = lambda: None

        with patch.object(NestJSClient, "http_client", new_callable=unittest.mock.PropertyMock) as mock_prop:
            mock_http = AsyncMock()
            mock_http.get.return_value = mock_resp
            mock_prop.return_value = mock_http

            gc = GraphClient(client)
            data = await gc.download_file("proj/test.pdf", "jwt_test")
            self.assertEqual(data, b"downloaded bytes")
            mock_http.get.assert_awaited_once()

    async def test_asave_document_uses_http_client_property(self):
        """Ensure asave_document uses .http_client property instead of uninitialized ._http_client."""
        from app.services.file_storage import asave_document
        from app.clients.nestjs_client import NestJSClient

        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = ""

        with patch.object(NestJSClient, "http_client", new_callable=unittest.mock.PropertyMock) as mock_prop:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_resp
            mock_prop.return_value = mock_http

            await asave_document("proj_test", "file_123", "Some content", {"orig": "test.txt"})
            mock_http.post.assert_awaited_once()

    async def test_consumer_handle_message_skips_on_404(self):
        """Ensure consumer skips processing immediately if backend reports 404."""
        from app.services.ingestion.consumer import handle_message
        import json

        mock_msg = AsyncMock()
        mock_msg.body = json.dumps({
            "pattern": "storage.file.uploaded",
            "data": {
                "fileId": "deleted_file_404",
                "key": "test.pdf",
                "projectId": "p1",
            }
        }).encode("utf-8")
        mock_msg.process = unittest.mock.MagicMock()
        mock_msg.process.return_value.__aenter__ = AsyncMock()
        mock_msg.process.return_value.__aexit__ = AsyncMock()

        mock_exchange = AsyncMock()

        with patch("app.services.ingestion.consumer.sync_status", new_callable=AsyncMock) as mock_sync, \
             patch("app.services.ingestion.consumer.process_file_pipeline", new_callable=AsyncMock) as mock_pipe:
            mock_sync.return_value = 404

            await handle_message(mock_msg, mock_exchange)

            mock_sync.assert_awaited_once_with("deleted_file_404", "p1", "processing")
            mock_pipe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
