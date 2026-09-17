"""Cancellation and active-status tracking for background file ingestion.

Extracted from rabbitmq_consumer.py. Manages:
- in-flight asyncio.Task registry for push-cancel on file deletion
- active_file_cache to avoid hammering NestJS internal API
- status sync fallback via NestJS internal API
"""
from __future__ import annotations

import asyncio
import time

from app.clients.nestjs_client import NestJSClient
from app.common.logger.logger import get_logger
from app.core.config import settings
from app.services.file_storage import delete_project_file

logger = get_logger("CancelTracker")

# Module-scope registries living for the lifetime of the consumer process
task_registry: dict[str, asyncio.Task] = {}
active_file_cache: dict[str, float] = {}
ACTIVE_CACHE_TTL_SEC = 30.0

_nestjs_client = NestJSClient(settings.NESTJS_API_URL)


async def sync_status(file_id: str, project_id: str, status: str) -> None:
    """Fallback path: PATCH status directly via NestJS internal API."""
    if not settings.MEMORA_INTERNAL_TOKEN:
        logger.warning("[sync_status] no MEMORA_INTERNAL_TOKEN configured; skipping")
        return
    try:
        code = await _nestjs_client.internal_patch(
            f"/internal/files/{file_id}/status",
            settings.MEMORA_INTERNAL_TOKEN,
            json={"status": status},
        )
        logger.info(f"[sync_status] PATCH {file_id} -> {status} = {code}")
    except Exception as e:
        logger.error(f"[sync_status] FAILED {file_id} -> {status}: {e}")


async def is_file_active(file_id: str, project_id: str) -> bool:
    """Cooperative cancel: returns False if file was deleted or cancelled."""
    now = time.monotonic()
    expiry = active_file_cache.get(file_id)
    if expiry is not None and expiry > now:
        return True
    if not settings.MEMORA_INTERNAL_TOKEN:
        return True

    try:
        data = await _nestjs_client.internal_get(
            f"/internal/files/{file_id}/status",
            settings.MEMORA_INTERNAL_TOKEN,
        )
        if data.get("_status") == 404:
            return False
        status = data.get("status")
        if status in ("cancelled", "failed"):
            return False
        active_file_cache[file_id] = now + ACTIVE_CACHE_TTL_SEC
        return True
    except Exception as e:
        logger.warning(f"[is_file_active] error for {file_id}: {e}")
        return True


def clear_active_cache(file_id: str) -> None:
    active_file_cache.pop(file_id, None)


async def on_file_deleted(file_id: str, project_id: str) -> None:
    """Push-cancel: cancel any in-flight task for this file and invalidate cache."""
    clear_active_cache(file_id)
    try:
        delete_project_file(project_id, file_id)
    except Exception as e:
        logger.warning(f"[on_file_deleted] local file cleanup failed for {file_id}: {e}")
    task = task_registry.pop(file_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.gather(task, return_exceptions=True)
        except Exception as e:
            logger.error(f"[on_file_deleted] gather error for {file_id}: {e}")
        logger.info(f"[on_file_deleted] cancelled task for {file_id}")
    else:
        logger.info(
            f"[on_file_deleted] no active task for {file_id} (already done or never started)"
        )
