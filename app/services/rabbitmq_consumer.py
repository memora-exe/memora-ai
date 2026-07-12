import asyncio
import json
import os
import tempfile
import time
import httpx
import aio_pika
from app.core.config import settings
from app.services.document_processor import process_document
from app.services.embedding_service import embedding_service
from app.services.vector_store import insert_chunks
from app.services.concept_extractor import extract_concepts
from app.services.graph_writer import write_graph

# Module-scope registries. Live for the lifetime of the consumer process.
# task_registry[file_id] = asyncio.Task for the in-flight handle_message
# coroutine, used by _on_file_deleted to push-cancel. active_file_cache
# short-circuits the GET /internal/files/:id/status check when the file
# was recently confirmed active.
task_registry: dict[str, asyncio.Task] = {}
active_file_cache: dict[str, float] = {}
ACTIVE_CACHE_TTL_SEC = 30.0


class FileCancelledError(Exception):
    """Raised when the file has been deleted mid-processing."""

    def __init__(self, file_id: str):
        super().__init__(f"File {file_id} cancelled")
        self.file_id = file_id


async def _sync_status(file_id: str, project_id: str, status: str) -> None:
    """Fallback path: PATCH status directly via NestJS internal API.

    Used only when RabbitMQ publish fails after retries. The internal token
    is shared via env (MEMORA_INTERNAL_TOKEN) and checked by
    InternalTokenGuard on the BE.
    """
    if not settings.MEMORA_INTERNAL_TOKEN:
        print(f"[sync_status] no MEMORA_INTERNAL_TOKEN configured; skipping", flush=True)
        return
    url = f"{settings.NESTJS_API_URL}/internal/files/{file_id}/status"
    headers = {
        "X-Internal-Token": settings.MEMORA_INTERNAL_TOKEN,
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient() as client:
            res = await client.patch(
                url, json={"status": status}, headers=headers, timeout=10.0
            )
            print(
                f"[sync_status] PATCH {file_id} → {status} = {res.status_code}",
                flush=True,
            )
    except Exception as e:
        print(f"[sync_status] FAILED {file_id} → {status}: {e}", flush=True)


async def _is_file_active(file_id: str, project_id: str) -> bool:
    """Cooperative cancel: returns False if file was deleted or marked cancelled.

    Cached as active for ACTIVE_CACHE_TTL_SEC to avoid hammering the API
    between every chunk. Cache is invalidated by _on_file_deleted so a
    freshly deleted file is caught on the next step.
    """
    now = time.monotonic()
    expiry = active_file_cache.get(file_id)
    if expiry is not None and expiry > now:
        return True
    if not settings.MEMORA_INTERNAL_TOKEN:
        # No token → can't check; assume active to avoid silent cancel on misconfig
        return True
    url = f"{settings.NESTJS_API_URL}/internal/files/{file_id}/status"
    headers = {"X-Internal-Token": settings.MEMORA_INTERNAL_TOKEN}
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(url, headers=headers, timeout=5.0)
            if res.status_code == 404:
                return False
            data = res.json()
            status = data.get("status")
            if status in ("cancelled", "failed"):
                return False
            active_file_cache[file_id] = now + ACTIVE_CACHE_TTL_SEC
            return True
    except Exception as e:
        print(f"[is_file_active] error for {file_id}: {e}", flush=True)
        # Network glitch: don't accidentally cancel — assume active.
        return True


def _clear_active_cache(file_id: str) -> None:
    active_file_cache.pop(file_id, None)


async def download_file(file_key: str, jwt_token: str) -> bytes:
    headers = {}
    if jwt_token:
        headers["Authorization"] = f"Bearer {jwt_token}"
    url = f"{settings.NESTJS_API_URL}/files/download/{file_key}"
    print(f"[download_file] GET {url}", flush=True)
    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=headers, timeout=60.0)
        print(
            f"[download_file] <- {res.status_code} ({len(res.content)} bytes)",
            flush=True,
        )
        res.raise_for_status()
        return res.content


async def publish_status(
    exchange,
    file_id: str,
    project_id: str,
    success: bool,
    error_msg: str = None,
):
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
            await exchange.publish(message, routing_key=routing_key, mandatory=True)
            print(
                f"[publish_status] {file_id} {pattern} ok (attempt {attempt + 1})",
                flush=True,
            )
            return
        except Exception as e:
            last_err = e
            wait = 2 ** attempt
            print(
                f"[publish_status] {file_id} {pattern} attempt {attempt + 1} failed: {e}; retry in {wait}s",
                flush=True,
            )
            await asyncio.sleep(wait)

    print(
        f"[publish_status] {file_id} all retries failed ({last_err}); using sync API fallback",
        flush=True,
    )
    # Fire-and-forget; the caller has already moved on.
    asyncio.create_task(
        _sync_status(file_id, project_id, "completed" if success else "failed")
    )


async def handle_message(message: aio_pika.IncomingMessage, exchange):
    """Process one uploaded file. Awaits synchronously inside its task."""
    async with message.process():
        file_id = None
        project_id = None
        cancelled = False
        tmp_path = None
        try:
            body = json.loads(message.body.decode())
            data = body.get("data", {})
            file_id = data.get("fileId")
            key = data.get("key")
            project_id = data.get("projectId")

            if not file_id or not key or not project_id:
                return

            print(f"Starting pipeline for file {file_id} (key: {key})", flush=True)

            jwt_token = os.getenv("SYSTEM_JWT_TOKEN", "")
            file_bytes = await download_file(key, jwt_token)

            with tempfile.NamedTemporaryFile(
                delete=False, suffix=os.path.splitext(key)[1]
            ) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            try:
                chunks = process_document(tmp_path)
                if not chunks:
                    raise Exception("No text content could be extracted from document.")

                # C3: cancel check before expensive embed
                if not await _is_file_active(file_id, project_id):
                    print(
                        f"[handle_message] {file_id} cancelled before embedding",
                        flush=True,
                    )
                    cancelled = True
                    raise FileCancelledError(file_id)

                embeddings = embedding_service.get_embeddings(chunks)

                # C3: cancel check before insert
                if not await _is_file_active(file_id, project_id):
                    print(
                        f"[handle_message] {file_id} cancelled before insert",
                        flush=True,
                    )
                    cancelled = True
                    raise FileCancelledError(file_id)

                db_chunks = []
                full_text = ""
                for idx, (content, emb) in enumerate(zip(chunks, embeddings)):
                    db_chunks.append(
                        {
                            "chunk_index": idx,
                            "content": content,
                            "embedding": emb,
                            "metadata": {"file_id": file_id, "project_id": project_id},
                        }
                    )
                    full_text += content + "\n"

                insert_chunks(file_id, project_id, db_chunks)

                # C3: cancel check before concept extract
                if not await _is_file_active(file_id, project_id):
                    print(
                        f"[handle_message] {file_id} cancelled before concept extract",
                        flush=True,
                    )
                    cancelled = True
                    raise FileCancelledError(file_id)

                extract_text = full_text[:50000]
                concepts = extract_concepts(extract_text)

                # C3: cancel check before graph write
                if not await _is_file_active(file_id, project_id):
                    print(
                        f"[handle_message] {file_id} cancelled before graph write",
                        flush=True,
                    )
                    cancelled = True
                    raise FileCancelledError(file_id)

                write_graph(project_id, jwt_token, concepts)

                await publish_status(exchange, file_id, project_id, True)
                print(f"Successfully processed file {file_id}")

            except FileCancelledError:
                # Don't publish processed/failed — job aborted.
                print(
                    f"FileCancelledError: skipping status publish for {file_id}",
                    flush=True,
                )

            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)

        except asyncio.CancelledError:
            # Push-cancel from _on_file_deleted. Don't ack inside the with-block;
            # message.process() context handles it on exit. Re-raise so
            # task_registry cleanup can run in the outer finally.
            print(
                f"handle_message task cancelled for {file_id}", flush=True
            )
            raise

        except Exception as e:
            print(f"Error processing file message: {str(e)}", flush=True)
            import traceback

            traceback.print_exc()
            if file_id and project_id and not cancelled:
                try:
                    await publish_status(exchange, file_id, project_id, False, str(e))
                except Exception as pe:
                    print(
                        f"Error publishing failure status: {str(pe)}", flush=True
                    )

        finally:
            if file_id:
                task_registry.pop(file_id, None)
                _clear_active_cache(file_id)


async def _on_file_deleted(file_id: str, project_id: str) -> None:
    """Push-cancel: cancel any in-flight task for this file and invalidate cache."""
    _clear_active_cache(file_id)
    task = task_registry.pop(file_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.gather(task, return_exceptions=True)
        except Exception as e:
            print(f"[_on_file_deleted] gather error for {file_id}: {e}", flush=True)
        print(f"[_on_file_deleted] cancelled task for {file_id}", flush=True)
    else:
        print(
            f"[_on_file_deleted] no active task for {file_id} (already done or never started)",
            flush=True,
        )


def _extract_file_id(message_body: bytes) -> str | None:
    try:
        return json.loads(message_body.decode()).get("data", {}).get("fileId")
    except Exception:
        return None


async def start_consumer():
    await asyncio.sleep(5)
    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    channel = await connection.channel()
    exchange = await channel.declare_exchange(
        "sk_repo_events", type="topic", durable=True
    )

    # Queue 1: file uploaded → start ingestion
    upload_queue = await channel.declare_queue(
        "sk_repo_ai_file_uploaded", durable=True
    )
    await upload_queue.bind(
        "sk_repo_events", routing_key="sk_repo.storage.file.uploaded"
    )
    print(
        "AI Consumer: listening on 'sk_repo_ai_file_uploaded'...", flush=True
    )

    # Queue 2: file deleted → cancel in-flight task
    delete_queue = await channel.declare_queue(
        "sk_repo_ai_file_deleted", durable=True
    )
    await delete_queue.bind(
        "sk_repo_events", routing_key="sk_repo.storage.file.deleted"
    )
    print(
        "AI Consumer: listening on 'sk_repo_ai_file_deleted' (cancel channel)...",
        flush=True,
    )

    async def consume_upload():
        async with upload_queue.iterator() as queue_iter:
            async for message in queue_iter:
                try:
                    body = json.loads(message.body.decode())
                    pattern = body.get("pattern")
                    if pattern == "storage.file.uploaded":
                        fid = _extract_file_id(message.body)
                        task = asyncio.create_task(handle_message(message, exchange))
                        if fid:
                            task_registry[fid] = task
                    else:
                        await message.ack()
                except Exception as e:
                    print(f"Error in upload consumer loop: {str(e)}", flush=True)
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
                        file_id = data.get("fileId")
                        project_id = data.get("projectId")
                        if file_id:
                            await _on_file_deleted(file_id, project_id)
                    except Exception as e:
                        print(f"Error in delete consumer: {str(e)}", flush=True)

    await asyncio.gather(consume_upload(), consume_delete())