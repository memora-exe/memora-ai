"""Document ingestion pipeline: download, parse, save, extract concepts, graph."""
from __future__ import annotations

import asyncio
import os
import tempfile

from app.clients.graph_client import GraphClient
from app.clients.nestjs_client import NestJSClient
from app.common.logger.logger import get_logger
from app.core.config import settings
from app.core.errors import FileCancelledError
from app.services.concept_extractor import extract_concepts
from app.services.document_processor import process_document
from app.services.file_storage import save_document
from app.services.ingestion.cancel_tracker import clear_active_cache, is_file_active, task_registry

logger = get_logger("IngestionPipeline")
_graph_client = GraphClient(NestJSClient(settings.NESTJS_API_URL))


async def process_file_pipeline(file_id: str, key: str, project_id: str, jwt_token: str) -> None:
    logger.info(f"Starting pipeline for file {file_id} (key: {key})")
    tmp_path = None
    try:
        file_bytes = await _graph_client.download_file(key, jwt_token)
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(key)[1]) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        chunks = process_document(tmp_path)
        if not chunks:
            raise ValueError("No text content could be extracted from document.")
        full_text = "\n".join(chunks)
        save_document(project_id, file_id, full_text, {
            "originalName": os.path.basename(key),
            "projectId": project_id,
        })

        if not await is_file_active(file_id, project_id):
            raise FileCancelledError(file_id)
        concepts = extract_concepts(full_text[:50000])
        if not await is_file_active(file_id, project_id):
            raise FileCancelledError(file_id)
        await _graph_client.write_graph(project_id, jwt_token, concepts)
        logger.info(f"Successfully processed file {file_id}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        task_registry.pop(file_id, None)
        clear_active_cache(file_id)
