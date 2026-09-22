"""Document ingestion pipeline: download, parse, save, extract concepts, graph."""
from __future__ import annotations

import asyncio
import os
import tempfile

from app.clients.graph_client import GraphClient
from app.clients.nestjs_client import get_shared_nestjs_client
from app.common.logger.logger import get_logger
from app.core.config import settings
from app.core.errors import FileCancelledError
from app.services.concept_extractor import aextract_concepts
from app.services.document_processor import extract_markdown
from app.services.file_storage import asave_document
from app.services.ingestion.cancel_tracker import clear_active_cache, is_file_active, task_registry

logger = get_logger("IngestionPipeline")
_graph_client = GraphClient(get_shared_nestjs_client())


async def process_file_pipeline(file_id: str, key: str, project_id: str, jwt_token: str) -> None:
    logger.info(f"Starting pipeline for file {file_id} (key: {key})")
    tmp_path = None
    try:
        file_bytes = await _graph_client.download_file(key, jwt_token)
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(key)[1]) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        full_text = await asyncio.to_thread(extract_markdown, tmp_path)
        if not full_text or not full_text.strip():
            raise ValueError("No text content could be extracted from document.")

        await asave_document(
            project_id,
            file_id,
            full_text,
            {
                "originalName": os.path.basename(key),
                "projectId": project_id,
            },
        )

        if not await is_file_active(file_id, project_id):
            raise FileCancelledError(file_id)

        concepts = await aextract_concepts(full_text)

        if not await is_file_active(file_id, project_id):
            raise FileCancelledError(file_id)

        await _graph_client.batch_write_graph(project_id, jwt_token, concepts)
        logger.info(f"Successfully processed file {file_id}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        task_registry.pop(file_id, None)
        clear_active_cache(file_id)
