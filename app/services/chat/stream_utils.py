"""Async iterator timeout wrapper — extracted from agent_service.py."""
from __future__ import annotations

import asyncio


async def aiter_with_timeout(async_iter, timeout: float):
    """Wrap any async iterator with a per-step timeout.

    Raises asyncio.TimeoutError if a single __anext__() exceeds `timeout`
    seconds. Use this instead of asyncio.wait_for(iter, timeout=...) because
    the latter wraps the coroutine, not the per-step await — and `async for`
    rejects a plain coroutine with TypeError.

    ponytail: replace with a context-manager timeout if we need an overall
    deadline (currently we only need idle-timeout protection).
    """
    iterator = async_iter.__aiter__()
    while True:
        try:
            yield await asyncio.wait_for(iterator.__anext__(), timeout=timeout)
        except StopAsyncIteration:
            return
