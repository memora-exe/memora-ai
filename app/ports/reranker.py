from abc import ABC, abstractmethod
from typing import List
from dataclasses import dataclass


@dataclass
class RankedDocumentData:
    index: int
    score: float
    document: str


class RerankerPort(ABC):
    """Abstract port for candidate reranking."""

    @abstractmethod
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: int = 0,
    ) -> List[RankedDocumentData]:
        """Score and rerank candidate documents against a query."""
        pass
