"""FastAPI dependency providers — injected via Depends() into route handlers.

Enables clean testing via app.dependency_overrides.
"""
from __future__ import annotations

from functools import lru_cache

from app.clients.graph_client import GraphClient
from app.clients.nestjs_client import NestJSClient
from app.core.config import settings
from app.repositories.session_repository import SessionRepository


@lru_cache
def get_nestjs_client() -> NestJSClient:
    return NestJSClient(base_url=settings.NESTJS_API_URL)


@lru_cache
def get_graph_client() -> GraphClient:
    return GraphClient(client=get_nestjs_client())


@lru_cache
def get_session_repo() -> SessionRepository:
    return SessionRepository(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
    )

