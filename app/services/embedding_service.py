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
        results: list[list[float]] = []
        # OpenAI /v1/embeddings accepts an array as `input`, but third-party
        # proxies (OpenRouter, Gemini compat, ...) often silently return
        # 200 OK with `data: []` for batched payloads even when a single
        # string returns valid data. Verified against
        # openrouter/nvidia/llama-nemotron-embed-vl-1b-v2:free on
        # kepter.id.vn:20128 — single input works, batch=100 returns empty.
        # Trade-off: more HTTP calls, far fewer empty-data failures.
        batch_size = 1
        # Errors that indicate a contract violation with the upstream provider
        # (200 OK but unparseable / empty body). Retrying won't help — bail
        # fast instead of burning 31s of backoff for the same broken payload.
        non_retryable = ("No embedding data received", "missing field", "data is not of type")
        retries = 3
        backoff = 1.0
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            for attempt in range(retries):
                try:
                    embeddings_batch = self.embeddings.embed_documents(batch)
                    results.extend(embeddings_batch)
                    break
                except Exception as e:
                    msg = str(e)
                    if any(token in msg for token in non_retryable):
                        print(
                            f"[embedding] non-retryable error on batch "
                            f"({len(batch)} chunks, attempt {attempt + 1}): {msg}",
                            flush=True,
                        )
                        raise
                    if attempt == retries - 1:
                        raise
                    time.sleep(backoff)
                    backoff *= 2.0
            backoff = 1.0
        return results

embedding_service = EmbeddingService()
