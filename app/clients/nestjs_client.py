"""Async HTTP client for the NestJS backend API.

Replaces 13 near-identical sync `requests` functions in graph_tools.py
with one generic async httpx client. Every graph / file / internal call
goes through `NestJSClient.request()`.
"""
from __future__ import annotations

import httpx

from app.common.logger.logger import get_logger
from app.core.errors import GraphAPIError

logger = get_logger("NestJSClient")

# Status codes considered success for write operations
_WRITE_OK = {200, 201}
_DELETE_OK = {200, 204}


class NestJSClient:
    """Async HTTP client for NestJS backend."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    # -- public helpers (thin wrappers) ------------------------------------

    async def get(self, path: str, jwt_token: str, **kwargs) -> dict | list:
        return await self.request("GET", path, jwt_token, **kwargs)

    async def post(self, path: str, jwt_token: str, **kwargs) -> dict | list:
        return await self.request("POST", path, jwt_token, ok_codes=_WRITE_OK, **kwargs)

    async def patch(self, path: str, jwt_token: str, **kwargs) -> dict | list:
        return await self.request("PATCH", path, jwt_token, ok_codes=_WRITE_OK, **kwargs)

    async def delete(self, path: str, jwt_token: str, **kwargs) -> dict | list:
        return await self.request("DELETE", path, jwt_token, ok_codes=_DELETE_OK, **kwargs)

    # -- core request method -----------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        jwt_token: str,
        *,
        ok_codes: set[int] | None = None,
        timeout: float | None = None,
        **kwargs,
    ) -> dict | list:
        """Single entry point — handles auth, error mapping, logging.

        Raises:
            GraphAPIError: on non-success status or network error.
        """
        if ok_codes is None:
            ok_codes = {200}
        url = f"{self._base_url}{path}"
        headers = {}
        if jwt_token:
            headers["Authorization"] = f"Bearer {jwt_token}"

        try:
            async with httpx.AsyncClient(timeout=timeout or self._timeout) as client:
                response = await client.request(method, url, headers=headers, **kwargs)
        except Exception as e:
            raise GraphAPIError(f"{method} {path} failed: {e}") from e

        if response.status_code in ok_codes:
            if response.status_code == 204:
                return {}
            return response.json()

        detail = response.text[:300] if response.text else ""
        raise GraphAPIError(
            f"{method} {path} returned {response.status_code}: {detail}",
            status_code=response.status_code,
        )

    # -- internal-token variant (for service-to-service calls) -------------

    async def internal_get(self, path: str, internal_token: str, *, timeout: float = 5.0) -> dict:
        """GET with X-Internal-Token header instead of Bearer."""
        url = f"{self._base_url}{path}"
        headers = {"X-Internal-Token": internal_token}
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, headers=headers)
        except Exception as e:
            raise GraphAPIError(f"internal GET {path} failed: {e}") from e
        if response.status_code == 404:
            return {"_status": 404}
        return response.json()

    async def internal_patch(self, path: str, internal_token: str, *, json: dict, timeout: float = 10.0) -> int:
        """PATCH with X-Internal-Token header. Returns status code."""
        url = f"{self._base_url}{path}"
        headers = {
            "X-Internal-Token": internal_token,
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.patch(url, headers=headers, json=json)
        except Exception as e:
            raise GraphAPIError(f"internal PATCH {path} failed: {e}") from e
        return response.status_code
