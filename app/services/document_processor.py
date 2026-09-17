"""Convert uploaded files to Markdown via MarkItDown before AI processing.

The previous version had per-extension branches (pypdf / python-docx / text
fallback). MarkItDown handles PDF, DOCX, PPTX, XLSX, HTML, images (with OCR),
audio, and plain text in a single pipeline, preserving document structure
(headings, lists, tables, code blocks) for downstream concept extraction.

`process_document()` keeps the same signature `(file_path: str) -> list[str]`
so callers (rabbitmq_consumer) don't need to change.
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter
from markitdown import MarkItDown

# Module-level singleton — initializing MarkItDown loads its converter registry
# (pdf, docx, pptx, xlsx, image OCR, ...). Reusing one instance avoids the import
# overhead on every uploaded file.
_MARKITDOWN = MarkItDown()

_SPLITTER = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)


def _to_markdown(file_path: str) -> str:
    result = _MARKITDOWN.convert(file_path)
    # `.markdown` is the canonical field; `.text_content` is the alias kept for
    # older markitdown releases.
    md = getattr(result, "markdown", None) or getattr(result, "text_content", "")
    if not md or not md.strip():
        raise ValueError(
            f"MarkItDown returned empty content for {file_path}. "
            "File may be unscannable (scanned PDF without OCR, corrupted, "
            "or unsupported format)."
        )
    return md


def process_document(file_path: str) -> list[str]:
    markdown = _to_markdown(file_path)
    return _SPLITTER.split_text(markdown)
