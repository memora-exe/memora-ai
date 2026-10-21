import math
import re
from typing import List, Set

from ...ports.reranker import RerankerPort, RankedDocumentData


class RerankerAdapter(RerankerPort):
    """Adapter for semantic/lexical candidate reranking."""

    def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: int = 0,
    ) -> List[RankedDocumentData]:
        if not documents:
            return []

        limit = top_n if top_n > 0 else len(documents)
        query_tokens = self._tokenize(query)

        scored_docs = []
        for idx, doc in enumerate(documents):
            score = self._compute_relevance_score(query, query_tokens, doc)
            scored_docs.append((idx, score, doc))

        scored_docs.sort(key=lambda item: item[1], reverse=True)
        top_results = scored_docs[:limit]

        return [
            RankedDocumentData(
                index=idx,
                score=float(score),
                document=doc,
            )
            for idx, score, doc in top_results
        ]

    def _tokenize(self, text: str) -> Set[str]:
        words = re.findall(r"\b\w+\b", text.lower())
        return set(words)

    def _compute_relevance_score(self, query: str, query_tokens: Set[str], doc: str) -> float:
        if not doc.strip() or not query_tokens:
            return 0.0

        doc_lower = doc.lower()
        doc_tokens = self._tokenize(doc)

        substring_boost = 0.3 if query.lower() in doc_lower else 0.0

        intersection = query_tokens.intersection(doc_tokens)
        token_score = len(intersection) / len(query_tokens) if query_tokens else 0.0

        tf_count = sum(doc_lower.count(token) for token in query_tokens)
        tf_score = math.tanh(tf_count / (len(doc_tokens) + 1) * 2.0)

        total_score = min(1.0, token_score * 0.5 + tf_score * 0.3 + substring_boost)
        return round(float(total_score), 4)


# Backward compatibility alias
RerankAdapter = RerankerAdapter

__all__ = ["RerankerAdapter", "RerankAdapter"]
