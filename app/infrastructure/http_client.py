"""
Shared async HTTP client for outbound calls (Auth, BRX_Search).
Connection pooling is used when the same client is reused; init at startup and close at shutdown.
Limits are read from config so high concurrency does not starve outbound requests.
"""
from typing import Optional

import httpx

from app.core.config import get_settings

_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    """Return the shared async client. Must call init_http_client() before first use."""
    if _client is None:
        raise RuntimeError("HTTP client not initialized; call init_http_client() at startup")
    return _client


def init_http_client(
    timeout: Optional[float] = None,
    limits: Optional[httpx.Limits] = None,
) -> httpx.AsyncClient:
    """Create and set the global async client. Idempotent: if already set, returns it.
    When timeout/limits are not passed, uses HTTP_* settings from config."""
    global _client
    if _client is not None:
        return _client
    settings = get_settings()
    _timeout = timeout if timeout is not None else settings.HTTP_TIMEOUT_SECONDS
    _limits = limits if limits is not None else httpx.Limits(
        max_keepalive_connections=settings.HTTP_KEEPALIVE_CONNECTIONS,
        max_connections=settings.HTTP_MAX_CONNECTIONS,
    )
    _client = httpx.AsyncClient(timeout=_timeout, limits=_limits)
    return _client


async def close_http_client() -> None:
    """Close the global client. No-op if not set."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
