"""
Redis async client (redis.asyncio) for cache, rate limiting, reindex queue.
Call init_redis() before any get_redis() / get_redis_optional() (e.g. in app lifespan or worker startup).
If init_redis() failed, _client is None: get_redis() raises RedisNotConnectedError; get_redis_optional() returns None.
"""
from typing import Optional

import redis.asyncio as redis
from loguru import logger

from app.core.config import get_settings

settings = get_settings()
_client: Optional[redis.Redis] = None


class RedisNotConnectedError(RuntimeError):
    """Raised when get_redis() is used but Redis was not initialized or connection failed."""

    def __init__(self) -> None:
        super().__init__("Redis not connected. Call init_redis() first and ensure it succeeded.")


async def init_redis() -> None:
    """Create Redis connection pool on startup. On failure, _client remains None."""
    global _client
    _client = redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
    )
    try:
        await _client.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning("Redis connection failed: {}", e)
        _client = None


async def close_redis() -> None:
    """Close Redis connection on shutdown."""
    global _client
    if _client:
        await _client.aclose()
        _client = None


async def check_redis_connected() -> bool:
    """Return True if Redis is reachable (for health check)."""
    if _client is None:
        return False
    try:
        await _client.ping()
        return True
    except Exception:
        return False


def get_redis() -> redis.Redis:
    """Return the shared Redis client. Raises RedisNotConnectedError if not initialized or connection failed."""
    if _client is None:
        raise RedisNotConnectedError()
    return _client


def get_redis_optional() -> Optional[redis.Redis]:
    """Return the shared Redis client or None if not connected. Use when Redis is optional (e.g. best-effort queue)."""
    return _client
