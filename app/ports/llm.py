from abc import ABC, abstractmethod
from typing import Dict, Iterator, List, Optional
from pydantic import BaseModel, Field


class ChatMessageData(BaseModel):
    role: str
    content: str


class ChatCompletionResult(BaseModel):
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = "stop"


class ChatStreamChunkResult(BaseModel):
    delta_content: str = ""
    is_done: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LlmPort(ABC):
    """Abstract port for large language model completions."""

    @abstractmethod
    def chat_completion(
        self,
        messages: List[ChatMessageData],
        model: str = "gemini-2.5-flash",
        temperature: float = 0.7,
    ) -> ChatCompletionResult:
        """Run non-streaming chat completion."""
        pass

    @abstractmethod
    def chat_completion_stream(
        self,
        messages: List[ChatMessageData],
        model: str = "gemini-2.5-flash",
        temperature: float = 0.7,
    ) -> Iterator[ChatStreamChunkResult]:
        """Stream chat completion chunks."""
        pass
