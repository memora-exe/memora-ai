"""Convert uploaded files to Markdown via MarkItDown before AI processing.

Preserves document structure (headings, lists, tables, code blocks)
and ensures clean, binary-free text output to avoid choking LLM context.
"""

from __future__ import annotations

import os
import re
from langchain_text_splitters import RecursiveCharacterTextSplitter
from markitdown import MarkItDown

# Module-level singleton — initializing MarkItDown loads its converter registry
# (pdf, docx, pptx, xlsx, image OCR, ...). Reusing one instance avoids the import
# overhead on every uploaded file.
_MARKITDOWN = MarkItDown()

_SPLITTER = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)


def clean_extracted_text(text: str) -> str:
    """Sanitize extracted document text, stripping null bytes, control chars and binary markers."""
    if not text or not isinstance(text, str):
        return ""
    # Strip null bytes and non-printable control characters (keep \n, \r, \t)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Detect raw binary PDF / PostScript dump
    if cleaned.lstrip().startswith(("%PDF-", "%!PS-Adobe")):
        return "[Binary PDF stream detected - text could not be extracted directly]"
    # Strip excessive replacement chars from corrupted encoding
    if cleaned.count("�") > 20:
        cleaned = cleaned.replace("�", "")
    return cleaned.strip()


def _extract_pdf_pypdf(file_path: str) -> str:
    """Fallback text extraction for PDF using pypdf when MarkItDown fails or returns raw binary."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        pages_text = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            text = clean_extracted_text(text)
            if text:
                pages_text.append(f"## Page {i + 1}\n\n{text}")
        return "\n\n".join(pages_text)
    except Exception:
        return ""


def _to_markdown(file_path: str) -> str:
    md = ""
    is_pdf = file_path.lower().endswith(".pdf")

    try:
        result = _MARKITDOWN.convert(file_path)
        md = getattr(result, "markdown", None) or getattr(result, "text_content", "")
    except Exception:
        if is_pdf:
            md = _extract_pdf_pypdf(file_path)

    # Fallback if empty or raw binary marker detected
    if not md or not md.strip() or md.lstrip().startswith("%PDF-"):
        if is_pdf:
            pypdf_text = _extract_pdf_pypdf(file_path)
            if pypdf_text:
                md = pypdf_text

    cleaned_md = clean_extracted_text(md)
    if not cleaned_md or cleaned_md.startswith("[Binary PDF stream"):
        raise ValueError(
            f"MarkItDown returned empty content for {file_path}. "
            "File may be unscannable (scanned PDF without OCR, corrupted, "
            "or unsupported format)."
        )
    return cleaned_md


def process_document(file_path: str) -> list[str]:
    markdown = _to_markdown(file_path)
    return _SPLITTER.split_text(markdown)
