import asyncio
import time
from typing import Awaitable, Callable

from app.core.config import settings, validate_embedding_dim
from app.services.llm import get_embedding_model

# Sanity-check embedding dim vs pgvector column at import time.
validate_embedding_dim()

# Errors that indicate a contract violation with the upstream provider
# (200 OK but unparseable / empty body). Retrying won't help — bail
# fast instead of burning backoff for the same broken payload.
_NON_RETRYABLE_TOKENS = (
    "No embedding data received",
    "missing field",
    "data is not of type",
)


class EmbeddingCancelledError(Exception):
    """Raised by aget_embeddings when the cancel predicate returns False."""


class EmbeddingService:
    def __init__(self):
        # OpenAI-API-spec dispatcher (refactored 2026-07-09).
        self.embeddings = get_embedding_model()

    def get_embedding(self, text: str) -> list[float]:
        return self.get_embeddings([text])[0]

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Sync path — kept only for callers that can't await. Slower than
        `aget_embeddings` because it serialises the per-chunk HTTP calls.
        Prefer `aget_embeddings` in any async pipeline (rabbitmq_consumer)."""
        results: list[list[float]] = []
        batch_size = max(1, settings.EMBED_BATCH_SIZE)
        retries = 3
        backoff = 1.0
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            for attempt in range(retries):
                try:
                    embeddings_batch = self.embeddings.embed_documents(batch)
                    results.extend(embeddings_batch)
                    break
                except Exception as e:
                    msg = str(e)
                    if any(token in msg for token in _NON_RETRYABLE_TOKENS):
                        raise
                    if attempt == retries - 1:
                        raise
                    time.sleep(backoff)
                    backoff *= 2.0
            backoff = 1.0
        return results

    async def aget_embeddings(
        self,
        texts: list[str],
        cancel: Callable[[], Awaitable[bool]] | None = None,
    ) -> list[list[float]]:
        """Async concurrent embedding. Splits texts into EMBED_BATCH_SIZE
        chunks, fans them out to EMBED_CONCURRENCY parallel HTTP calls.

        Args:
            texts: chunk strings to embed.
            cancel: optional async predicate. After every concurrent window
                    we await `await cancel()`; if it returns False we raise
                    EmbeddingCancelledError — caller should treat as cancel
                    and stop the rest of the pipeline. Shielded internally
                    so the check itself can't be cancelled.

        Raises:
            EmbeddingCancelledError: cancel predicate returned False.
            Exception: any provider error after retry budget exhausted.
        """
        if not texts:
            return []

        batch_size = max(1, settings.EMBED_BATCH_SIZE)
        concurrency = max(1, settings.EMBED_CONCURRENCY)
        retries = 3
        # Pre-slice so each "task" is a fixed batch (no re-slicing after the
        # first batch fails — we want the result list order to match `texts`).
        batches: list[list[str]] = [
            texts[i : i + batch_size] for i in range(0, len(texts), batch_size)
        ]
        results: list[list[float] | None] = [None] * len(batches)
        # Windowed fan-out — semaphore caps live requests; sliding window
        # ensures a single failed batch doesn't stall the whole pipeline.
        sem = asyncio.Semaphore(concurrency)
        index_iter = iter(range(len(batches)))

        async def _run_one(idx: int, batch: list[str]) -> None:
            backoff = 1.0
            for attempt in range(retries):
                try:
                    embeddings_batch = await self.embeddings.aembed_documents(batch)
                    results[idx] = embeddings_batch
                    return
                except Exception as e:
                    msg = str(e)
                    if any(token in msg for token in _NON_RETRYABLE_TOKENS):
                        raise
                    if attempt == retries - 1:
                        raise
                    await asyncio.sleep(backoff)
                    backoff *= 2.0

        async def _drain() -> None:
            pending: set[asyncio.Task] = set()
            for idx in index_iter:
                await sem.acquire()
                # Cancel checkpoint between windows (cheap, no DB call if
                # cancel is None — `_is_file_active` short-circuits the
                # network check via `active_file_cache`).
                if cancel is not None:
                    try:
                        still_active = await asyncio.shield(cancel())
                    except Exception:
                        still_active = True  # never cancel on check failure
                    if not still_active:
                        sem.release()
                        raise EmbeddingCancelledError("cancel predicate returned False")
                task = asyncio.create_task(_run_one(idx, batches[idx]))
                pending.add(task)
                task.add_done_callback(lambda t, s=sem: s.release())
            if pending:
                await asyncio.gather(*pending, return_exceptions=False)

        if settings.EMBED_STAGE_TIMEOUT_SEC > 0:
            await asyncio.wait_for(_drain(), timeout=settings.EMBED_STAGE_TIMEOUT_SEC)
        else:
            await _drain()

        # Flatten preserving order; results are guaranteed populated because
        # _drain raised otherwise.
        flat: list[list[float]] = []
        for batch_result in results:
            assert batch_result is not None
            flat.extend(batch_result)
        return flat


embedding_service = EmbeddingService()