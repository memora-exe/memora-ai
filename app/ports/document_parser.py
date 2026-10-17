from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class DocumentChunkData:
    chunk_index: int
    content: str
    start_char: int
    end_char: int
    metadata: Dict[str, str]


@dataclass
class DocumentMetadataData:
    page_count: int
    word_count: int
    title: str
    detected_language: str


@dataclass
class ParsedDocumentResult:
    markdown_content: str
    chunks: List[DocumentChunkData]
    metadata: DocumentMetadataData


class DocumentParserPort(ABC):
    """Abstract port for document parsing."""

    @abstractmethod
    def parse_document(
        self,
        file_content: bytes,
        file_name: str = "document",
        mime_type: str = "",
        options: Optional[Dict[str, str]] = None,
    ) -> ParsedDocumentResult:
        """Parse document content into markdown, chunks, and metadata."""
        pass
