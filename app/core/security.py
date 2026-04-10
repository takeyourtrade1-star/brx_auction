"""
JWT RS256 validation. Tokens are issued by BRX_auth; we validate with public key.
Public key is re-read periodically (JWT_KEY_REFRESH_SECONDS) so rotation works without restart.
Async path uses asyncio.Lock so key refresh does not block the event loop; jwt.decode and
key parsing run in a dedicated thread pool to avoid blocking on CPU-bound work.
"""
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import jwt
from jwt import DecodeError, InvalidTokenError

from app.core.config import Settings, get_settings

# Cache: (key_bytes, timestamp). Refreshed when TTL expires so key rotation is picked up.
_key_cache: Optional[tuple[bytes, float]] = None
# asyncio.Lock: avoids blocking the event loop while waiting for key refresh (threading.Lock would block).
_key_cache_lock = asyncio.Lock()

# Dedicated executor for JWT decode and key loading; sized from config to handle high concurrency.
_jwt_executor: Optional[ThreadPoolExecutor] = None


def _get_jwt_executor() -> ThreadPoolExecutor:
    global _jwt_executor
    if _jwt_executor is None:
        workers = get_settings().JWT_EXECUTOR_MAX_WORKERS
        _jwt_executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="jwt")
    return _jwt_executor


def get_jwt_executor() -> ThreadPoolExecutor:
    """Return the dedicated JWT executor (e.g. for startup key loading). Creates it if needed."""
    return _get_jwt_executor()


def shutdown_jwt_executor() -> None:
    """Call at app shutdown to release the dedicated JWT thread pool."""
    global _jwt_executor
    if _jwt_executor is not None:
        _jwt_executor.shutdown(wait=False)
        _jwt_executor = None


def _format_pem_key(key_str: str, is_private: bool = False) -> bytes:
    """Ensure PEM has proper headers and newlines."""
    key_str = (key_str or "").strip()
    if not key_str:
        raise ValueError("Empty key")
    if "-----BEGIN" in key_str:
        return key_str.encode("utf-8")
    header = "-----BEGIN PRIVATE KEY-----" if is_private else "-----BEGIN PUBLIC KEY-----"
    footer = "-----END PRIVATE KEY-----" if is_private else "-----END PUBLIC KEY-----"
    lines = [line.strip() for line in key_str.replace(header, "").replace(footer, "").split() if line.strip()]
    return (header + "\n" + "\n".join(lines) + "\n" + footer).encode("utf-8")


def _load_key_from_settings(settings: Settings) -> bytes:
    """Parse and return public key bytes from settings."""
    key_str = settings.JWT_PUBLIC_KEY
    if not key_str:
        raise ValueError("JWT_PUBLIC_KEY not configured")
    return _format_pem_key(key_str, is_private=False)


def _should_refresh(settings: Settings) -> bool:
    """True if cache is missing or older than JWT_KEY_REFRESH_SECONDS. Caller must hold _key_cache_lock when reading _key_cache."""
    if _key_cache is None:
        return True
    ttl = settings.JWT_KEY_REFRESH_SECONDS
    if ttl <= 0:
        return False
    return (time.monotonic() - _key_cache[1]) >= ttl


def load_public_key() -> bytes:
    """Load JWT public key and prime cache. Called at startup (sync) to fail fast if misconfigured."""
    global _key_cache
    settings = get_settings()
    key_bytes = _load_key_from_settings(settings)
    _key_cache = (key_bytes, time.monotonic())
    return key_bytes


async def get_public_key_bytes() -> bytes:
    """Return current public key; re-read from config when TTL expires. Key loading runs in executor to avoid blocking the event loop."""
    global _key_cache
    settings = get_settings()
    async with _key_cache_lock:
        if _should_refresh(settings):
            loop = asyncio.get_event_loop()
            key_bytes = await loop.run_in_executor(_get_jwt_executor(), lambda: _load_key_from_settings(settings))
            _key_cache = (key_bytes, time.monotonic())
        return _key_cache[0]


async def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate JWT (signature + exp). Runs signature verification in a thread pool
    so the event loop is not blocked (RSA is CPU-bound).
    Raises InvalidTokenError or DecodeError on failure.
    Returns payload dict; use payload['sub'] for user_id.
    """
    settings = get_settings()
    key = await get_public_key_bytes()

    def _decode() -> dict[str, Any]:
        return jwt.decode(
            token,
            key,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": True, "verify_signature": True},
        )

    loop = asyncio.get_event_loop()
    payload = await loop.run_in_executor(_get_jwt_executor(), _decode)
    if payload.get("type") != "access":
        raise InvalidTokenError("Token type must be access")
    return payload
