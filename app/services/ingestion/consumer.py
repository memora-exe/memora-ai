"""RabbitMQ consumer for file upload and delete events.

Extracted from rabbitmq_consumer.py. Handles:
- queue connection, declaration, binding
- event dispatching to IngestionPipeline or CancelTracker
- status publishing with retry and sync fallback
"""
from __future__ import annotations

import asyncio
import json
import os

import aio_pika

from app.common.logger.logger import get_logger
from app.core.config import settings
from app.core.errors import FileCancelledError
from app.services.ingestion.cancel_tracker import (
    on_file_deleted,
    sync_status,
    task_registry,
)
from app.services.ingestion.pipeline import process_file_pipeline

logger = get_logger("RabbitMQConsumer")
_semaphore: asyncio.Semaphore | None = None


def get_ingestion_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.INGESTION_CONCURRENCY)
    return _semaphore


async def publish_status(
    exchange,
    file_id: str,
    project_id: str,
    success: bool,
    error_msg: str = None,
) -> None:
    """Publish ai.document.processed|failed with retry; fallback to sync API."""
    pattern = "ai.document.processed" if success else "ai.document.failed"
    routing_key = "sk_repo.ai.document.processed" if success else "sk_repo.ai.document.failed"
    payload = {
        "pattern": pattern,
        "data": {
            "fileId": file_id,
            "projectId": project_id,
            **({"error": error_msg} if error_msg else {}),
        },
    }
    message = aio_pika.Message(
        body=json.dumps(payload).encode("utf-8"),
        content_type="application/json",
    )

    last_err = None
    for attempt in range(3):
        try:
            await exchange.publish(message, routing_key=routing_key)
            logger.info(f"[publish_status] {file_id} {pattern} ok (attempt {attempt + 1})")
            return
        except Exception as e:
            last_err = e
            wait = 2 ** attempt
            logger.warning(
                f"[publish_status] {file_id} {pattern} attempt {attempt + 1} failed: {e}; retry in {wait}s"
            )
            await asyncio.sleep(wait)

    logger.error(
        f"[publish_status] {file_id} all retries failed ({last_err}); using sync API fallback"
    )
    asyncio.create_task(
        sync_status(file_id, project_id, "completed" if success else "failed")
    )


async def handle_message(message: aio_pika.IncomingMessage, exchange) -> None:
    """Process one uploaded file message with semaphore gating and status tracking."""
    semaphore = get_ingestion_semaphore()
    async with semaphore:
        async with message.process():
            file_id = None
            project_id = None
            cancelled = False
            try:
                body = json.loads(message.body.decode())
                data = body.get("data", {})
                file_id = data.get("fileId")
                key = data.get("key")
                project_id = data.get("projectId")

                if not file_id or not key or not project_id:
                    return

                # Immediately notify BE that processing has started
                try:
                    code = await sync_status(file_id, project_id, "processing")
                    if code == 404:
                        logger.info(
                            f"[handle_message] File {file_id} not found on backend (404), skipping ingestion"
                        )
                        return
                except Exception as status_err:
                    logger.warning(f"Failed to update status to processing for {file_id}: {status_err}")

                jwt_token = os.getenv("SYSTEM_JWT_TOKEN", "")
                try:
                    # Enforce hard 120s timeout on whole ingestion pipeline
                    pipeline_timeout = float(
                        getattr(settings, "INGESTION_PIPELINE_TIMEOUT_SEC", 120)
                    )
                    await asyncio.wait_for(
                        process_file_pipeline(file_id, key, project_id, jwt_token),
                        timeout=pipeline_timeout,
                    )
                    await publish_status(exchange, file_id, project_id, True)
                except FileCancelledError:
                    logger.info(f"[handle_message] skipping status publish for cancelled {file_id}")
                    cancelled = True
                except (asyncio.TimeoutError, TimeoutError) as te:
                    logger.error(
                        f"Pipeline timed out after {pipeline_timeout}s for file {file_id}: {te}"
                    )
                    if file_id and project_id:
                        # Immediately sync failed status to PostgreSQL and push SSE
                        await sync_status(file_id, project_id, "failed")
                        try:
                            await publish_status(
                                exchange,
                                file_id,
                                project_id,
                                False,
                                f"Pipeline timed out after {pipeline_timeout}s",
                            )
                        except Exception as pe:
                            logger.error(f"Error publishing timeout failure status: {pe}")
                    cancelled = True

            except asyncio.CancelledError:
                logger.info(f"handle_message task cancelled for {file_id}")
                raise
            except Exception as e:
                logger.error(f"Error processing file message: {e}", exc_info=True)
                if file_id and project_id and not cancelled:
                    # Sync failed status immediately via internal API
                    try:
                        await sync_status(file_id, project_id, "failed")
                    except Exception as se:
                        logger.error(f"Error syncing failed status: {se}")
                    try:
                        await publish_status(exchange, file_id, project_id, False, str(e))
                    except Exception as pe:
                        logger.error(f"Error publishing failure status: {pe}")
            finally:
                if file_id:
                    task_registry.pop(file_id, None)
                    clear_active_cache(file_id)



def _extract_file_id(message_body: bytes) -> str | None:
    try:
        return json.loads(message_body.decode()).get("data", {}).get("fileId")
    except Exception:
        return None


async def start_consumer() -> None:
    """Entry point — connects to RabbitMQ and starts consumption loops."""
    if not settings.RABBITMQ_ENABLED:
        logger.info("RabbitMQ is disabled (RABBITMQ_ENABLED=false). Skipping consumer.")
        return

    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    channel = await connection.channel()
    prefetch = max(settings.INGESTION_CONCURRENCY * 2, 4)
    await channel.set_qos(prefetch_count=prefetch)

    exchange = await channel.declare_exchange(
        "sk_repo_events", type="topic", durable=True
    )

    # Queue 1: file uploaded -> start ingestion
    upload_queue = await channel.declare_queue(
        "sk_repo_ai_file_uploaded", durable=True
    )
    await upload_queue.bind(
        "sk_repo_events", routing_key="sk_repo.storage.file.uploaded"
    )
    logger.info("AI Consumer: listening on 'sk_repo_ai_file_uploaded'...")

    # Queue 2: file deleted -> cancel in-flight task
    delete_queue = await channel.declare_queue(
        "sk_repo_ai_file_deleted", durable=True
    )
    await delete_queue.bind(
        "sk_repo_events", routing_key="sk_repo.storage.file.deleted"
    )
    logger.info("AI Consumer: listening on 'sk_repo_ai_file_deleted' (cancel channel)...")

    async def consume_upload():
        async with upload_queue.iterator() as queue_iter:
            async for message in queue_iter:
                try:
                    body = json.loads(message.body.decode())
                    if body.get("pattern") == "storage.file.uploaded":
                        fid = _extract_file_id(message.body)
                        task = asyncio.create_task(handle_message(message, exchange))
                        if fid:
                            task_registry[fid] = task
                    else:
                        await message.ack()
                except Exception as e:
                    logger.error(f"Error in upload consumer loop: {e}")
                    try:
                        await message.ack()
                    except Exception:
                        pass

    async def consume_delete():
        async with delete_queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        body = json.loads(message.body.decode())
                        data = body.get("data", {})
                        fid = data.get("fileId")
                        pid = data.get("projectId")
                        if fid:
                            await on_file_deleted(fid, pid)
                    except Exception as e:
                        logger.error(f"Error in delete consumer: {e}")

    await asyncio.gather(consume_upload(), consume_delete())
