"""Unit tests for flashcard generator service."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.clients.graph_client import GraphClient
from app.services.flashcard_generator import generate_flashcards_from_nodes


class TestFlashcardsGenerator(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_graph_client = MagicMock(spec=GraphClient)
        self.mock_nodes = [
            {
                "id": "node-1",
                "nodeName": "Binary Search",
                "note": "A divide-and-conquer search algorithm with O(log n) complexity.",
                "data": {},
            },
            {
                "id": "node-2",
                "nodeName": "Sorted Array",
                "note": "An array where elements are in non-decreasing order.",
                "data": {},
            },
        ]
        self.mock_edges = [
            {
                "sourceId": "node-2",
                "targetId": "node-1",
                "edgeTypeId": "PREREQUISITE",
            }
        ]
        self.mock_graph_client.get_nodes = AsyncMock(return_value=self.mock_nodes)
        self.mock_graph_client.get_edges = AsyncMock(return_value=self.mock_edges)

    @patch("app.services.flashcard_generator.get_chat_model")
    async def test_generate_flashcards_with_prompt(self, mock_get_chat_model):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = (
            '{"cards": [{"front": "How does Binary Search require Sorted Array?", '
            '"back": "Sorted array allows logarithmic divide-and-conquer steps.", '
            '"nodeId": "node-1", "sourceRelation": "PREREQUISITE"}]}'
        )
        mock_get_chat_model.return_value = mock_llm

        cards = await generate_flashcards_from_nodes(
            project_id="proj-1",
            node_ids=["node-1", "node-2"],
            count=1,
            jwt_token="mock-jwt",
            graph_client=self.mock_graph_client,
            prompt="Focus on prerequisite relationships and algorithm complexity",
        )

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["front"], "How does Binary Search require Sorted Array?")
        self.assertEqual(cards[0]["nodeId"], "node-1")
        mock_llm.invoke.assert_called_once()
        call_prompt = mock_llm.invoke.call_args[0][0]
        self.assertIn("Focus on prerequisite relationships and algorithm complexity", call_prompt)

    @patch("app.services.flashcard_generator.get_chat_model")
    async def test_generate_flashcards_without_prompt(self, mock_get_chat_model):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = (
            '{"cards": [{"front": "What is Binary Search?", '
            '"back": "A divide-and-conquer search algorithm.", '
            '"nodeId": "node-1", "sourceRelation": "DEFINES"}]}'
        )
        mock_get_chat_model.return_value = mock_llm

        cards = await generate_flashcards_from_nodes(
            project_id="proj-1",
            node_ids=["node-1"],
            count=1,
            jwt_token="mock-jwt",
            graph_client=self.mock_graph_client,
            prompt=None,
        )

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["front"], "What is Binary Search?")
        mock_llm.invoke.assert_called_once()
        call_prompt = mock_llm.invoke.call_args[0][0]
        self.assertNotIn("Additional pedagogical instructions from user", call_prompt)

    @patch("app.services.flashcard_generator.get_chat_model")
    async def test_generate_flashcards_llm_exception_fallback(self, mock_get_chat_model):
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("LLM provider unavailable or timeout")
        mock_get_chat_model.return_value = mock_llm

        cards = await generate_flashcards_from_nodes(
            project_id="proj-1",
            node_ids=["node-1", "node-2"],
            count=2,
            jwt_token="mock-jwt",
            graph_client=self.mock_graph_client,
            prompt="Make them tricky",
        )

        # Fallback to heuristic generation
        self.assertEqual(len(cards), 2)
        # Verify heuristic output structure
        for card in cards:
            self.assertIn("front", card)
            self.assertIn("back", card)
            self.assertIn("nodeId", card)
            self.assertIn("sourceRelation", card)


if __name__ == "__main__":
    unittest.main()
