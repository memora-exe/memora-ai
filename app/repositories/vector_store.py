"""pgvector document_chunk repository — connection pool + insert/search.

Refactored from services/vector_store.py:
- Added SimpleConnectionPool (was creating a new connection per call)
- Same public API: insert_chunks(), search(), get_db_connection()
"""
import psycopg2
import psycopg2.extras
import psycopg2.pool
from pgvector.psycopg2 import register_vector

from app.core.config import settings

# ponytail: SimpleConnectionPool is thread-safe for get/put but not for
# concurrent use of a single connection. Since FastAPI runs in a single
# event loop thread (sync DB calls block it anyway), this is fine.
# Upgrade to asyncpg + pgvector when async-all-the-way matters.
_pool: psycopg2.pool.SimpleConnectionPool | None = None


def _get_pool() -> psycopg2.pool.SimpleConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        _pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
        )
    return _pool


def get_db_connection():
    """Get a pooled connection with pgvector registered.

    Caller MUST call `release_connection(conn)` when done (or use as
    context manager via `with _pooled_conn() as conn:`).
    """
    conn = _get_pool().getconn()
    register_vector(conn)
    return conn


def release_connection(conn) -> None:
    """Return a connection to the pool."""
    try:
        _get_pool().putconn(conn)
    except Exception:
        # Pool closed or connection already returned — ignore.
        try:
            conn.close()
        except Exception:
            pass


class _PooledConn:
    """Context manager that auto-releases connection back to pool."""

    def __enter__(self):
        self.conn = get_db_connection()
        return self.conn

    def __exit__(self, *exc):
        release_connection(self.conn)
        return False


def pooled_conn() -> _PooledConn:
    return _PooledConn()


def insert_chunks(file_id: str, project_id: str, chunks: list) -> None:
    """Insert document chunks with embeddings into pgvector."""
    with pooled_conn() as conn:
        with conn.cursor() as cur:
            for chunk in chunks:
                metadata_val = chunk.get("metadata", {})
                cur.execute(
                    """
                    INSERT INTO document_chunk (id, file_id, project_id, chunk_index, content, metadata, embedding)
                    VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        file_id,
                        project_id,
                        chunk["chunk_index"],
                        chunk["content"],
                        psycopg2.extras.Json(metadata_val),
                        chunk["embedding"],
                    ),
                )
        conn.commit()


def search(project_id: str, query_embedding: list, k: int = 10) -> list:
    """Cosine-distance search on document_chunk embeddings."""
    with pooled_conn() as conn:
        with conn.cursor() as cur:
            vec_str = "[" + ",".join(str(float(x)) for x in query_embedding) + "]"
            cur.execute(
                """
                SELECT id, file_id, chunk_index, content, metadata, embedding <=> %s::vector as distance
                FROM document_chunk
                WHERE project_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vec_str, project_id, vec_str, k),
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "file_id": r[1],
                    "chunk_index": r[2],
                    "content": r[3],
                    "metadata": r[4],
                    "distance": r[5],
                }
                for r in rows
            ]
