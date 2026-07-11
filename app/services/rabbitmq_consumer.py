import asyncio
import json
import os
import tempfile
import httpx
import aio_pika
from app.core.config import settings
from app.services.document_processor import process_document
from app.services.embedding_service import embedding_service
from app.services.vector_store import insert_chunks
from app.services.concept_extractor import extract_concepts
from app.services.graph_writer import write_graph

async def download_file(file_key: str, jwt_token: str) -> bytes:
    headers = {}
    if jwt_token:
        headers["Authorization"] = f"Bearer {jwt_token}"

    url = f"{settings.NESTJS_API_URL}/files/download/{file_key}"
    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=headers, timeout=60.0)
        res.raise_for_status()
        return res.content

async def publish_status(channel, file_id: str, project_id: str, success: bool, error_msg: str = None):
    pattern = "ai.document.processed" if success else "ai.document.failed"
    routing_key = "sk_repo.ai.document.processed" if success else "sk_repo.ai.document.failed"
    payload = {
        "pattern": pattern,
        "data": {
            "fileId": file_id,
            "projectId": project_id,
            **({"error": error_msg} if error_msg else {})
        }
    }

    message = aio_pika.Message(
        body=json.dumps(payload).encode("utf-8"),
        content_type="application/json"
    )
    exchange = await channel.get_exchange("sk_repo_events")
    await exchange.publish(message, routing_key=routing_key)

async def handle_message(message: aio_pika.IncomingMessage):
    async with message.process():
        file_id = None
        project_id = None
        try:
            body = json.loads(message.body.decode())
            data = body.get("data", {})
            file_id = data.get("fileId")
            key = data.get("key")
            project_id = data.get("projectId")

            if not file_id or not key or not project_id:
                return

            print(f"Starting pipeline for file {file_id} (key: {key})")

            jwt_token = os.getenv("SYSTEM_JWT_TOKEN", "")
            file_bytes = await download_file(key, jwt_token)

            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(key)[1]) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            try:
                chunks = process_document(tmp_path)
                if not chunks:
                    raise Exception("No text content could be extracted from document.")

                embeddings = embedding_service.get_embeddings(chunks)

                db_chunks = []
                full_text = ""
                for idx, (content, emb) in enumerate(zip(chunks, embeddings)):
                    db_chunks.append({
                        "chunk_index": idx,
                        "content": content,
                        "embedding": emb,
                        "metadata": {"file_id": file_id, "project_id": project_id}
                    })
                    full_text += content + "\n"

                insert_chunks(file_id, project_id, db_chunks)

                extract_text = full_text[:50000]
                concepts = extract_concepts(extract_text)

                write_graph(project_id, jwt_token, concepts)

                # Use message's channel to publish status
                await publish_status(message.channel, file_id, project_id, True)
                print(f"Successfully processed file {file_id}")

            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        except Exception as e:
            print(f"Error processing file message: {str(e)}")
            if file_id and project_id:
                try:
                    await publish_status(message.channel, file_id, project_id, False, str(e))
                except Exception as pe:
                    print(f"Error publishing failure status: {str(pe)}")

async def start_consumer():
    await asyncio.sleep(5)
    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    channel = await connection.channel()
    await channel.declare_exchange("sk_repo_events", type="topic", durable=True)
    queue = await channel.declare_queue("sk_repo_default", durable=True)
    await queue.bind("sk_repo_events", routing_key="sk_repo.#")

    print("AI Consumer started. Listening on 'sk_repo_default' queue...")
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            try:
                body = json.loads(message.body.decode())
                pattern = body.get("pattern")
                if pattern == "storage.file.uploaded":
                    # Process in a background task so we don't block receipt of other events
                    asyncio.create_task(handle_message(message))
                else:
                    await message.ack()
            except Exception as e:
                print(f"Error in consumer loop: {str(e)}")
