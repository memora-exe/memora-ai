import time
from app.core.config import settings, validate_embedding_dim
from app.services.llm import get_embedding_model

# Sanity-check embedding dim vs pgvector column at import time.
validate_embedding_dim()


class EmbeddingService:
    def __init__(self):
        # OpenAI-API-spec dispatcher (refactored 2026-07-09).
        # Default returns OpenAIEmbeddings(OPENAI_EMBED_MODEL) — same wire format
        # regardless of which provider sits behind OPENAI_EMBED_BASE_URL.
        self.embeddings = get_embedding_model()

    def get_embedding(self, text: str) -> list[float]:
        return self.get_embeddings([text])[0]

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        results = []
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            retries = 5
            backoff = 1.0
            for attempt in range(retries):
                try:
                    # Retrieve embeddings for the batch
                    embeddings_batch = self.embeddings.embed_documents(batch)
                    results.extend(embeddings_batch)
                    break
                except Exception as e:
                    if attempt == retries - 1:
                        raise e
                    time.sleep(backoff)
                    backoff *= 2.0
        return results

embedding_service = EmbeddingService()
