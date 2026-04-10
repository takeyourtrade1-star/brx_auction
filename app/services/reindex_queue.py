"""
Push reindex requests to Redis queue. Worker (separate process or background task) consumes and calls BRX_Search.
Uses Redis list (LPUSH / BRPOP) or Redis Streams; here we use a simple list key.
"""
from typing import Optional

from loguru import logger

from app.core.config import get_settings
from app.infrastructure.redis_client import get_redis_optional

try:
    import redis.exceptions as _redis_exceptions
    _REINDEX_REDIS_ERRORS = (_redis_exceptions.RedisError, _redis_exceptions.ConnectionError, _redis_exceptions.TimeoutError, OSError)
except ImportError:
    _REINDEX_REDIS_ERRORS = (OSError,)

settings = get_settings()
QUEUE_KEY = settings.REDIS_REINDEX_QUEUE


async def enqueue_reindex(reason: str = "manual") -> bool:
    """Push a reindex request to Redis. Returns True if pushed, False if Redis unavailable."""
    redis = get_redis_optional()
    if not redis:
        return False
    try:
        await redis.lpush(QUEUE_KEY, reason)
        return True
    except _REINDEX_REDIS_ERRORS as e:
        logger.warning("Reindex enqueue failed (Redis): {} {}", type(e).__name__, e)
        return False


# Blocking pop timeout: short so new messages are picked up quickly (no extra sleep in worker).
BRPOP_TIMEOUT_SECONDS = 1


async def consume_reindex_queue() -> Optional[str]:
    """Blocking pop one reindex request from the queue. Returns reason or None. Used by worker."""
    redis = get_redis_optional()
    if not redis:
        return None
    try:
        result = await redis.brpop(QUEUE_KEY, timeout=BRPOP_TIMEOUT_SECONDS)
        if result:
            return result[1]
        return None
    except _REINDEX_REDIS_ERRORS as e:
        logger.warning("Reindex consume failed (Redis): {} {}", type(e).__name__, e)
        return None
