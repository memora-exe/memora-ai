from abc import ABC, abstractmethod
from typing import List, Tuple
from dataclasses import dataclass


@dataclass
class EmbeddingResult:
    vectors: List[List[float]]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class EmbedderPort(ABC):
    """Abstract port for vector embedding generation."""

    @abstractmethod
    def generate_embeddings(
        self,
        texts: List[str],
        model: str = "text-embedding-004",
        dimensions: int = 768,
    ) -> EmbeddingResult:
        """Generate dense vector embeddings for input texts."""
        pass
