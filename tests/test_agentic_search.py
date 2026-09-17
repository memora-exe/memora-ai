"""Integration and unit tests for agentic search tools, routes, and security."""
import unittest
from unittest.mock import MagicMock, patch

from app.services.file_storage import (
    _safe_resolve,
    delete_project_file,
    grep_documents,
    list_documents,
    read_document,
    save_document,
)
from app.services.chat.tool_builder import build_graph_tools
from tests.test_file_storage import MockBackendStorage


class TestSecurityPathTraversal(unittest.TestCase):
    def test_path_traversal_variations(self):
        cases = [
            "../../../etc/passwd",
            "/etc/passwd",
            "\\etc\\passwd",
            "test/../../../etc/passwd",
            "..",
            ".hidden",
            "a/../../b",
            "C:\\Windows\\System32",
            "//host/share/file",
            "a/b.md",
            "a\\b.md",
        ]
        for c in cases:
            with self.subTest(case=c):
                with self.assertRaises(ValueError):
                    _safe_resolve("proj_test", c)


class TestAgentChatTools(unittest.TestCase):
    def setUp(self):
        self.mock_backend = MockBackendStorage()
        self.patcher = patch("app.services.file_storage._request", side_effect=self.mock_backend)
        self.patcher.start()

        self.project_id = "test_agent_project"
        self.jwt_token = "mock_jwt"
        self.session_id = "mock_session"

        # Mock GraphClient
        self.mock_gc = MagicMock()
        self.tools = build_graph_tools(
            self.project_id,
            self.jwt_token,
            self.session_id,
            graph_client=self.mock_gc,
        )
        self.tools_by_name = {t.__name__: t for t in self.tools}

    def tearDown(self):
        self.patcher.stop()

    def test_tool_presence(self):
        self.assertIn("llm_glob_files", self.tools_by_name)
        self.assertIn("llm_grep_search", self.tools_by_name)
        self.assertIn("llm_read_file_content", self.tools_by_name)
        self.assertNotIn("llm_search_vector", self.tools_by_name)
        self.assertNotIn("llm_search_hybrid", self.tools_by_name)
        create_edge_doc = self.tools_by_name["llm_create_edge"].__doc__
        self.assertNotIn("llm_search_hybrid", create_edge_doc)
        self.assertIn("llm_grep_search", create_edge_doc)

    def test_metadata_tracker_preserves_mutations_and_normalizes_matches(self):
        from app.services.chat.metadata_tracker import (
            build_citation_metadata,
            clear_metadata,
            get_metadata,
            record_mutation,
            set_metadata,
        )

        clear_metadata(self.project_id, self.session_id)
        record_mutation(self.project_id, self.session_id, "created", nodes=["node_1"])
        set_metadata(self.project_id, self.session_id, {
            "fileMatches": [{
                "file_id": "doc_1",
                "original_name": "doc_1.md",
                "line_number": 10,
                "snippet": "10: content",
            }]
        })

        raw = get_metadata(self.project_id, self.session_id)
        self.assertIn("mutatedEntities", raw)
        self.assertEqual(raw["mutatedEntities"]["created"]["nodes"], ["node_1"])

        citation = build_citation_metadata(raw)
        self.assertEqual(citation["fileMatches"], [{
            "id": "doc_1",
            "content": "10: content",
            "metadata": {
                "file_id": "doc_1",
                "original_name": "doc_1.md",
                "line_number": 10,
                "snippet": "10: content",
            },
        }])
        self.assertEqual(citation["chunks"], citation["fileMatches"])
        self.assertEqual(citation["mutatedEntities"]["created"]["nodes"], ["node_1"])

    def test_tool_execution_flow(self):
        # Step 1: Save document
        file_id = "doc_test_1"
        save_document(
            self.project_id,
            file_id,
            "Title: Memora Architecture\nSection 1: Agentic file search replaces pgvector.\nSection 2: Ripgrep and Glob.",
            metadata={"originalName": "arch.md"},
        )

        # Step 2: glob_files
        glob_fn = self.tools_by_name["llm_glob_files"]
        file_list = glob_fn()
        self.assertEqual(len(file_list), 1)
        self.assertEqual(file_list[0]["file_id"], file_id)
        self.assertEqual(file_list[0]["original_name"], "arch.md")

        # Step 3: grep_search
        grep_fn = self.tools_by_name["llm_grep_search"]
        matches = grep_fn("Agentic file search")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["file_id"], file_id)
        self.assertEqual(matches[0]["line_number"], 2)

        # Step 4: read_file_content
        read_fn = self.tools_by_name["llm_read_file_content"]
        read_res = read_fn(file_id, offset=1, limit=2)
        self.assertEqual(read_res["file_id"], file_id)
        self.assertEqual(read_res["total_lines"], 3)
        self.assertEqual(read_res["content"], "Title: Memora Architecture\nSection 1: Agentic file search replaces pgvector.")


if __name__ == "__main__":
    unittest.main()
