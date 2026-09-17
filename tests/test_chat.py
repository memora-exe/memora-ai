"""Test chat endpoints and chat service integration."""
import json
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


class TestChatEndpoints(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._orig_storage = settings.STORAGE_BASE_DIR
        settings.STORAGE_BASE_DIR = self._temp_dir.name
        self.client = TestClient(app)

    def tearDown(self):
        settings.STORAGE_BASE_DIR = self._orig_storage
        self._temp_dir.cleanup()

    @patch("app.api.routes.chat.process_chat_message", new_callable=AsyncMock)
    def test_chat_non_stream(self, mock_process_chat):
        mock_process_chat.return_value = ("Hello there!", {"sources": []})
        response = self.client.post(
            "/api/chat/",
            json={
                "message": "hello",
                "session_id": "sess_1",
                "project_id": "proj_1",
                "jwt_token": "token_1",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["reply"], "Hello there!")
        self.assertEqual(data["tool_calls"], {"sources": []})
        mock_process_chat.assert_called_once()

    @patch("app.api.routes.chat.process_chat_message_stream")
    def test_chat_stream(self, mock_process_stream):
        async def mock_stream_generator(*args, **kwargs):
            yield "Hello "
            yield "world!"
            yield {"metadata": {"citations": []}}

        mock_process_stream.return_value = mock_stream_generator()

        response = self.client.post(
            "/api/chat/stream",
            json={
                "message": "hello stream",
                "session_id": "sess_2",
                "project_id": "proj_2",
                "jwt_token": "token_2",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers.get("content-type", ""))
        body = response.text
        self.assertIn("Hello ", body)
        self.assertIn("world!", body)


if __name__ == "__main__":
    unittest.main()
