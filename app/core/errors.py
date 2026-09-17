"""Typed exceptions for the Memora AI service.

Routes catch MemoraError subclasses and map them to HTTPException.
Services raise these instead of returning {"error": "..."} dicts.
"""


class MemoraError(Exception):
    """Base exception for all Memora AI errors."""


class GraphAPIError(MemoraError):
    """NestJS graph proxy returned a non-success status."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class FileCancelledError(MemoraError):
    """File was deleted or cancelled mid-processing."""

    def __init__(self, file_id: str):
        super().__init__(f"File {file_id} cancelled")
        self.file_id = file_id


class LLMTimeoutError(MemoraError):
    """LLM call or chat turn exceeded its deadline."""

    def __init__(self, message: str, timeout_sec: float):
        super().__init__(message)
        self.timeout_sec = timeout_sec
