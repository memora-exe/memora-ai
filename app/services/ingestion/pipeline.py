"""Document ingestion pipeline — extracted from rabbitmq_consumer.py.

Orchestrates: download -> parse -> embed -> insert chunks -> extract concepts -> write graph.
Uses cooperative cancel checkpoints between expensive stages.
"""
from __future__ import annotations

import asyncio
import os
import tempfile

from app.clients.graph_client import GraphClient
from app.clients.nestjs_client import NestJSClient
from app.common.logger.logger import get_logger
from app.core.config import settings
from app.core.errors import FileCancelledError
from app.repositories.vector_store import insert_chunks
from app.services.concept_extractor import extract_concepts
from app.services.document_processor import process_document
from app.services.embedding_service import EmbeddingCancelledError, embedding_service
from app.services.ingestion.cancel_tracker import (
    clear_active_cache,
    is_file_active,
    task_registry,
)

logger = get_logger("IngestionPipeline")

_graph_client = GraphClient(NestJSClient(settings.NESTJS_API_URL))


async def process_file_pipeline(
    file_id: str,
    key: str,
    project_id: str,
    jwt_token: str,
) -> None:
    """Execute the full document ingestion pipeline for one file."""
    logger.info(f"Starting pipeline for file {file_id} (key: {key})")
    tmp_path = None

    try:
        file_bytes = await _graph_client.download_file(key, jwt_token)

        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(key)[1]
        ) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        chunks = process_document(tmp_path)
        if not chunks:
            raise ValueError("No text content could be extracted from document.")

        # C1: cancel check before expensive embed
        if not await is_file_active(file_id, project_id):
            logger.info(f"[pipeline] {file_id} cancelled before embedding")
            raise FileCancelledError(file_id)

        embeddings = await embedding_service.aget_embeddings(
            chunks,
            cancel=lambda: is_file_active(file_id, project_id),
        )

        # C2: cancel check before insert
        if not await is_file_active(file_id, project_id):
            logger.info(f"[pipeline] {file_id} cancelled before insert")
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
        if not await is_file_active(file_id, project_id):
            logger.info(f"[pipeline] {file_id} cancelled before concept extract")
            raise FileCancelledError(file_id)

        extract_text = full_text[:50000]
        concepts = extract_concepts(extract_text)

        # C4: cancel check before graph write
        if not await is_file_active(file_id, project_id):
            logger.info(f"[pipeline] {file_id} cancelled before graph write")
            raise FileCancelledError(file_id)

        await _graph_client.write_graph(project_id, jwt_token, concepts)
        logger.info(f"Successfully processed file {file_id}")

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        task_registry.pop(file_id, None)
        clear_active_cache(file_id)
