"""Unit tests for file storage client, path traversal sandbox, and backend integration."""
import unittest
from unittest.mock import patch

from app.services.file_storage import (
    _parse_rg_output,
    _project_dir,
    _safe_resolve,
    delete_project_file,
    grep_documents,
    list_documents,
    read_document,
    read_full_text,
    save_document,
)


class MockBackendStorage:
    def __init__(self):
        self.files = {}

    def __call__(self, method: str, path: str, **kwargs):
        if method == "POST" and "/parsed" in path:
            json_body = kwargs.get("json", {})
            file_id = path.split("/")[3]
            project_id = json_body.get("projectId")
            self.files[(project_id, file_id)] = {
                "fileId": file_id,
                "projectId": project_id,
                "content": json_body.get("content", ""),
                "metadata": json_body.get("metadata", {}),
            }
            return {"ok": True, "fileId": file_id, "projectId": project_id}

        if method == "GET" and "/project/" in path and "/parsed" in path:
            project_id = path.split("/")[4]
            results = []
            for (p_id, f_id), data in sorted(self.files.items()):
                if p_id == project_id:
                    results.append({
                        "file_id": f_id,
                        "original_name": data["metadata"].get("originalName", f"{f_id}.md"),
                        "size_bytes": len(data["content"].encode("utf-8")),
                    })
            return results

        if method == "GET" and "/parsed" in path:
            file_id = path.split("/")[3]
            project_id = kwargs.get("params", {}).get("projectId")
            key = (project_id, file_id)
            if key not in self.files:
                return {"_status": 404, "error": "Not found"}
            return self.files[key]

        if method == "DELETE" and "/parsed" in path:
            file_id = path.split("/")[3]
            project_id = kwargs.get("params", {}).get("projectId")
            self.files.pop((project_id, file_id), None)
            return {"ok": True}

        return {}


class TestFileStorage(unittest.TestCase):
    def setUp(self):
        self.mock_backend = MockBackendStorage()
        self.patcher = patch("app.services.file_storage._request", side_effect=self.mock_backend)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_safe_resolve_valid(self):
        path = _safe_resolve("proj_1", "doc1.md")
        self.assertEqual(path.name, "doc1.md")
        self.assertIn("proj_1", str(path))

    def test_safe_resolve_blocks_traversal(self):
        bad_names = [
            "../../../etc/passwd",
            "/etc/passwd",
            "\\etc\\passwd",
            "test/../../../etc/passwd",
            "..",
            ".hidden",
            "",
            "../doc.md",
            "..\\doc.md",
            "a/b.md",
            "a\\b.md",
        ]
        for bad_name in bad_names:
            with self.subTest(bad_name=bad_name):
                with self.assertRaises(ValueError):
                    _safe_resolve("proj_1", bad_name)

    def test_invalid_project_id(self):
        bad_projs = ["..", ".", "a/b", "a\\b", ""]
        for bad_proj in bad_projs:
            with self.subTest(bad_proj=bad_proj):
                with self.assertRaises(ValueError):
                    _project_dir(bad_proj)

    def test_save_and_read_document(self):
        project_id = "test_project"
        file_id = "file_123"
        content = "Line 1\nLine 2: Target keyword\nLine 3\nLine 4\nLine 5"
        meta = {"originalName": "source_doc.pdf", "size": 100}

        save_document(project_id, file_id, content, metadata=meta)
        self.assertIn((project_id, file_id), self.mock_backend.files)

        # Read with offset/limit
        res = read_document(project_id, file_id, offset=2, limit=2)
        self.assertEqual(res["file_id"], file_id)
        self.assertEqual(res["original_name"], "source_doc.pdf")
        self.assertEqual(res["total_lines"], 5)
        self.assertEqual(res["offset"], 2)
        self.assertEqual(res["limit"], 2)
        self.assertEqual(res["content"], "Line 2: Target keyword\nLine 3")

        # Also works when passing .md extension
        res_ext = read_document(project_id, f"{file_id}.md", offset=1, limit=2)
        self.assertEqual(res_ext["file_id"], file_id)
        self.assertEqual(res_ext["total_lines"], 5)

        # Full text
        self.assertEqual(read_full_text(project_id, file_id), content)
        self.assertEqual(read_full_text(project_id, f"{file_id}.md"), content)

    def test_read_document_not_found(self):
        res = read_document("test_project", "missing_file")
        self.assertIn("error", res)

    def test_list_documents(self):
        project_id = "test_list_proj"
        save_document(project_id, "doc_a", "Content A", {"originalName": "A.pdf"})
        save_document(project_id, "doc_b", "Content B", {"originalName": "B.docx"})

        docs = list_documents(project_id)
        self.assertEqual(len(docs), 2)
        file_ids = {d["file_id"] for d in docs}
        self.assertEqual(file_ids, {"doc_a", "doc_b"})

        with self.assertRaises(ValueError):
            list_documents(project_id, pattern="../../*")

    def test_parse_rg_output(self):
        output = "rg_proj/doc_1.md-1-Intro\nrg_proj/doc_1.md:2:Important discovery\nrg_proj/doc_1.md-3-Conclusion"
        matches = _parse_rg_output("rg_proj", output, 50)
        self.assertEqual(matches, [{
            "file_id": "doc_1",
            "original_name": "doc_1.md",
            "line_number": 2,
            "snippet": "1: Intro\n2: Important discovery\n3: Conclusion",
        }])

    def test_grep_documents(self):
        project_id = "test_grep_proj"
        save_document(project_id, "doc_1", "Intro\nImportant discovery on quantum computing\nConclusion")
        save_document(project_id, "doc_2", "History\nClassical physics only\nEnd")

        matches = grep_documents(project_id, "quantum")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["file_id"], "doc_1")
        self.assertEqual(matches[0]["line_number"], 2)
        self.assertIn("quantum computing", matches[0]["snippet"])

        # Case insensitive by default
        matches_ci = grep_documents(project_id, "QUANTUM")
        self.assertEqual(len(matches_ci), 1)

        # Case sensitive search
        matches_cs = grep_documents(project_id, "QUANTUM", case_sensitive=True)
        self.assertEqual(len(matches_cs), 0)

        # Pattern traversal blocked
        with self.assertRaises(ValueError):
            grep_documents(project_id, "test", path_pattern="../../*.md")

    def test_delete_project_file(self):
        project_id = "test_del_proj"
        file_id = "to_delete"
        save_document(project_id, file_id, "Some text", metadata={"originalName": "del.txt"})

        self.assertTrue(delete_project_file(project_id, file_id))
        self.assertEqual(read_full_text(project_id, file_id), "")
        self.assertEqual(list_documents(project_id), [])


if __name__ == "__main__":
    unittest.main()
