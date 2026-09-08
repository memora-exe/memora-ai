# DEPRECATED: Re-exported from app.repositories.vector_store
from app.repositories.vector_store import (
    get_db_connection,
    insert_chunks,
    pooled_conn,
    release_connection,
    search,
)

__all__ = ["get_db_connection", "insert_chunks", "search", "pooled_conn", "release_connection"]
