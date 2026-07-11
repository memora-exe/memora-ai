import json
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.common.logger.logger import get_logger

# Mirror the NestJS backend format:
#   [HTTP] Incoming Request: POST /path - Body: {...}
#   [HTTP] Outgoing Response: POST /path 200 - 18ms
class HttpLoggerMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, logger_name: str = "HTTP") -> None:
        super().__init__(app)
        self.logger = get_logger(logger_name)

    async def dispatch(self, request: Request, call_next):
        body = await self._safe_body(request)
        self.logger.info(
            f"Incoming Request: {request.method} {request.url.path} - "
            f"Body: {body}"
        )
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        self.logger.info(
            f"Outgoing Response: {request.method} {request.url.path} "
            f"{response.status_code} - {duration_ms}ms"
        )
        return response

    @staticmethod
    async def _safe_body(request: Request):
        try:
            body_bytes = await request.body()
            if not body_bytes:
                return "undefined"
            text = body_bytes.decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text)
                text = json.dumps(parsed, ensure_ascii=False)
            except json.JSONDecodeError:
                pass
            if len(text) > 500:
                text = text[:500] + "...(truncated)"
            return text
        except Exception:
            return "undefined"
