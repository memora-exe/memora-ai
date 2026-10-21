import hashlib
from typing import List

import numpy as np

from ...ports.embedder import EmbedderPort, EmbeddingResult
from ..config.settings import settings


class EmbedderAdapter(EmbedderPort):
    """Adapter for generating dense vector embeddings."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or settings.gemini_api_key

    def generate_embeddings(
        self,
        texts: List[str],
        model: str = "text-embedding-004",
        dimensions: int = 768,
    ) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=[], prompt_tokens=0, completion_tokens=0, total_tokens=0)

        model_name = model or "text-embedding-004"
        dim = dimensions if dimensions > 0 else 768
        total_tokens = sum(len(t.split()) for t in texts)

        vectors_data: List[List[float]] = []

        if self.api_key:
            try:
                from langchain_google_genai import GoogleGenerativeAIEmbeddings

                embedder = GoogleGenerativeAIEmbeddings(
                    model=model_name,
                    google_api_key=self.api_key,
                )
                embeddings = embedder.embed_documents(texts)
                for emb in embeddings:
                    if len(emb) != dim and dim > 0:
                        if len(emb) > dim:
                            emb = emb[:dim]
                        else:
                            emb = emb + [0.0] * (dim - len(emb))
                    vectors_data.append(emb)
            except Exception:
                vectors_data = [self._local_embedding(t, dim) for t in texts]
        else:
            vectors_data = [self._local_embedding(t, dim) for t in texts]

        return EmbeddingResult(
            vectors=vectors_data,
            prompt_tokens=total_tokens,
            completion_tokens=0,
            total_tokens=total_tokens,
        )

    def _local_embedding(self, text: str, dimensions: int) -> List[float]:
        rng = np.random.RandomState(int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16))
        vec = rng.randn(dimensions).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()


# Backward compatibility alias
EmbeddingAdapter = EmbedderAdapter

__all__ = ["EmbedderAdapter", "EmbeddingAdapter"]
