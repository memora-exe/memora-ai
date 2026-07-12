import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
from app.core.config import settings

def get_db_connection():
    conn = psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME
    )
    register_vector(conn)
    return conn

def insert_chunks(file_id: str, project_id: str, chunks: list):
    # chunks list of dict: {"chunk_index": int, "content": str, "embedding": list[float], "metadata": dict}
    conn = get_db_connection()
    try:
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
                        chunk["embedding"]
                    )
                )
        conn.commit()
    finally:
        conn.close()

def search(project_id: str, query_embedding: list, k=10) -> list:
    conn = get_db_connection()
    try:
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
                (vec_str, project_id, vec_str, k)
            )
            rows = cur.fetchall()
            results = []
            for r in rows:
                results.append({
                    "id": r[0],
                    "file_id": r[1],
                    "chunk_index": r[2],
                    "content": r[3],
                    "metadata": r[4],
                    "distance": r[5]
                })
            return results
    finally:
        conn.close()
