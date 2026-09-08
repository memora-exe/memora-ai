"""Document chunk DB queries — extracted from document_reader and document_topic_extractor.

Centralizes all direct document_chunk SELECT queries so routes/services
don't each open their own psycopg2 connections.
"""
from __future__ import annotations

from typing import List

from app.repositories.vector_store import pooled_conn


def fetch_chunks_by_file(file_id: str) -> List[str]:
    """Return ordered chunk texts for a single file. Used by document_reader."""
    with pooled_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_index, content FROM document_chunk "
                "WHERE file_id = %s ORDER BY chunk_index",
                (file_id,),
            )
            return [r[1] for r in cur.fetchall() if r[1]]


def load_chunk_text(file_ids: List[str], budget: int) -> str:
    """Concatenate chunk content across files, truncated to `budget` chars.

    Used by document_topic_extractor for roadmap topic extraction.
    """
    with pooled_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT file_id, chunk_index, content
                FROM document_chunk
                WHERE file_id = ANY(%s)
                ORDER BY file_id, chunk_index
                """,
                (file_ids,),
            )
            rows = cur.fetchall()

    parts: list[str] = []
    remaining = budget
    for row in rows:
        content = row[2] or ""
        if not content or remaining <= 0:
            continue
        if len(content) <= remaining:
            parts.append(content)
            remaining -= len(content)
        else:
            parts.append(content[:remaining])
            remaining = 0
    return "\n\n".join(parts)
