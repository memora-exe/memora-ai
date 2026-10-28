import io
import os
import re
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
import docx
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ...ports.document_parser import (
    DocumentParserPort,
    ParsedDocumentResult,
    DocumentChunkData,
    DocumentMetadataData,
)


class DocumentParserAdapter(DocumentParserPort):
    """Adapter for parsing documents using PyMuPDF and python-docx."""

    def parse_document(
        self,
        file_content: bytes,
        file_name: str = "document",
        mime_type: str = "",
        options: Optional[Dict[str, str]] = None,
    ) -> ParsedDocumentResult:
        options = options or {}
        chunk_size = int(options.get("chunk_size", 1000))
        chunk_overlap = int(options.get("chunk_overlap", 200))

        ext = os.path.splitext(file_name)[1].lower()
        title = os.path.splitext(file_name)[0]

        try:
            if ext == ".pdf" or "pdf" in mime_type.lower():
                markdown_content, page_count, pdf_title = self._parse_pdf(file_content)
                if pdf_title:
                    title = pdf_title
            elif ext in [".docx", ".doc"] or "wordprocessingml" in mime_type.lower() or "msword" in mime_type.lower():
                markdown_content, page_count = self._parse_docx(file_content)
            else:
                markdown_content = self._parse_text(file_content)
                page_count = 1
        except Exception as e:
            markdown_content = f"# Error parsing document\n\n{str(e)}"
            page_count = 0

        words = re.findall(r"\b\w+\b", markdown_content)
        word_count = len(words)
        detected_language = self._detect_language(markdown_content)

        chunks = self._create_chunks(markdown_content, chunk_size, chunk_overlap)

        return ParsedDocumentResult(
            markdown_content=markdown_content,
            chunks=chunks,
            metadata=DocumentMetadataData(
                page_count=page_count,
                word_count=word_count,
                title=title,
                detected_language=detected_language,
            ),
        )

    def _parse_pdf(self, content: bytes) -> Tuple[str, int, str]:
        doc = fitz.open(stream=content, filetype="pdf")
        page_count = len(doc)
        title = doc.metadata.get("title", "") if doc.metadata else ""

        pages_text = []
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            if text:
                pages_text.append(f"## Page {i + 1}\n\n{text}")

        markdown_content = "\n\n".join(pages_text)
        return markdown_content, page_count, title

    def _parse_docx(self, content: bytes) -> Tuple[str, int]:
        doc_file = io.BytesIO(content)
        doc = docx.Document(doc_file)
        paragraphs = []
        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue
            if p.style.name.startswith("Heading 1"):
                paragraphs.append(f"# {text}")
            elif p.style.name.startswith("Heading 2"):
                paragraphs.append(f"## {text}")
            elif p.style.name.startswith("Heading 3"):
                paragraphs.append(f"### {text}")
            else:
                paragraphs.append(text)

        markdown_content = "\n\n".join(paragraphs)
        page_count = max(1, len(markdown_content) // 3000 + 1)
        return markdown_content, page_count

    def _parse_text(self, content: bytes) -> str:
        for enc in ["utf-8", "utf-8-sig", "latin-1"]:
            try:
                return content.decode(enc)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="replace")

    def _detect_language(self, text: str) -> str:
        if not text:
            return "en"
        vi_chars = set("àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ")
        if any(c in vi_chars for c in text.lower()):
            return "vi"
        return "en"

    def _create_chunks(self, text: str, chunk_size: int, chunk_overlap: int) -> List[DocumentChunkData]:
        if not text.strip():
            return []

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", " ", ""],
        )

        raw_chunks = splitter.split_text(text)
        chunks = []
        current_offset = 0

        for i, chunk_text in enumerate(raw_chunks):
            start_char = text.find(chunk_text, current_offset)
            if start_char == -1:
                start_char = current_offset
            end_char = start_char + len(chunk_text)
            current_offset = max(start_char, current_offset)

            chunks.append(
                DocumentChunkData(
                    chunk_index=i,
                    content=chunk_text,
                    start_char=start_char,
                    end_char=end_char,
                    metadata={"chunk_size": str(len(chunk_text))},
                )
            )

        return chunks
