"""Redis session store — renamed from services/session_manager.py.

Same logic, just moved to repositories/ for layer clarity.
"""
import json

import redis

from app.core.config import settings


class SessionRepository:
    def __init__(
        self,
        host: str = None,
        port: int = None,
        ttl: int = 86400,
    ):
        self.client = redis.Redis(
            host=host or settings.REDIS_HOST,
            port=port or settings.REDIS_PORT,
            decode_responses=True,
        )
        self.ttl = ttl  # 24 hours sliding TTL

    def _get_key(self, session_id: str) -> str:
        return f"ai:session:{session_id}"

    def get_messages(self, session_id: str) -> list:
        key = self._get_key(session_id)
        data = self.client.get(key)
        self.client.expire(key, self.ttl)  # Slide TTL on access
        if not data:
            return []
        try:
            return json.loads(data)
        except Exception:
            return []

    def save_messages(self, session_id: str, messages: list) -> None:
        key = self._get_key(session_id)
        self.client.setex(key, self.ttl, json.dumps(messages))

    def append_message(self, session_id: str, role: str, content: str) -> None:
        messages = self.get_messages(session_id)
        messages.append({"role": role, "content": content})
        self.save_messages(session_id, messages)

    def clear_session(self, session_id: str) -> None:
        self.client.delete(self._get_key(session_id))


# Default instance — will be replaced by dependency injection in Phase 6
session_repository = SessionRepository()
