"""
Optional Redis cache for read-heavy GET-by-id responses. Fail-safe: if Redis is unavailable, no cache.
Keys are JSON-serializable; values are dicts stored as JSON (datetime/UUID as string).
Call invalidate_cached after writes so readers see fresh data.
Single-flight loading lock per key to avoid thundering herd on cache miss.
"""
import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, Optional

from loguru import logger

from app.infrastructure.redis_client import get_redis_optional

# TTL in seconds for GET-by-id cache (short to avoid stale data when invalidation is missed).
CACHE_TTL_SECONDS = 60
# Max size of cached value in bytes to avoid storing huge payloads (Redis/memory DoS).
CACHE_VALUE_MAX_BYTES = 512 * 1024

# Fixed-size pool of locks: key (prefix, id) maps to bucket hash % size. Bounded memory; keys in same bucket serialize (acceptable).
CACHE_LOCK_POOL_SIZE = 4096
_load_locks_pool: list[asyncio.Lock] = [asyncio.Lock() for _ in range(CACHE_LOCK_POOL_SIZE)]


def _lock_bucket(prefix: str, id: int) -> asyncio.Lock:
    """Return the lock for this cache key (same bucket for keys that hash to same index)."""
    bucket = abs(hash((prefix, id))) % CACHE_LOCK_POOL_SIZE
    return _load_locks_pool[bucket]


@asynccontextmanager
async def loading_lock(prefix: str, id: int):
    """
    Async context manager: one coroutine per bucket loads; others in same bucket wait then can read cache.
    Use after get_cached returns None: async with loading_lock(prefix, id): double-check get_cached, then load and set_cached.
    Fixed pool size avoids unbounded memory; hash collision only serializes loads for keys in same bucket.
    """
    lock = _lock_bucket(prefix, id)
    await lock.acquire()
    try:
        yield
    finally:
        lock.release()


def _serialize(value: dict[str, Any]) -> str:
    return json.dumps(value, default=str)


def _deserialize(raw: str) -> dict[str, Any]:
    return json.loads(raw)


try:
    import redis.exceptions as _redis_exceptions
    _REDIS_ERRORS: tuple[type[BaseException], ...] = (
        _redis_exceptions.RedisError,
        _redis_exceptions.ConnectionError,
        _redis_exceptions.TimeoutError,
        OSError,
    )
except ImportError:
    _REDIS_ERRORS = (OSError,)


async def get_cached(prefix: str, id: int) -> Optional[dict[str, Any]]:
    """Return cached dict if present and Redis available, else None. Skips values larger than CACHE_VALUE_MAX_BYTES."""
    redis = get_redis_optional()
    if not redis:
        return None
    key = f"ebartex:cache:{prefix}:{id}"
    try:
        raw = await redis.get(key)
        if raw is None:
            return None
        if len(raw) > CACHE_VALUE_MAX_BYTES:
            logger.debug("Cache get skipped (value too large): prefix={} id={} size={}", prefix, id, len(raw))
            return None
        return _deserialize(raw)
    except _REDIS_ERRORS as e:
        logger.warning("Cache get failed: prefix={} id={} error={}", prefix, id, e)
        return None


async def set_cached(prefix: str, id: int, value: dict[str, Any], ttl: int = CACHE_TTL_SECONDS) -> None:
    """Store value in cache. No-op if Redis unavailable, value too large, or on error."""
    redis = get_redis_optional()
    if not redis:
        return
    key = f"ebartex:cache:{prefix}:{id}"
    try:
        payload = _serialize(value)
        if len(payload) > CACHE_VALUE_MAX_BYTES:
            logger.debug("Cache set skipped (value too large): prefix={} id={} size={}", prefix, id, len(payload))
            return
        await redis.setex(key, ttl, payload)
    except _REDIS_ERRORS as e:
        logger.warning("Cache set failed: prefix={} id={} error={}", prefix, id, e)


async def invalidate_cached(prefix: str, id: int) -> None:
    """Remove cached entry so next read hits the DB. Call after updating or deleting the resource."""
    redis = get_redis_optional()
    if not redis:
        return
    key = f"ebartex:cache:{prefix}:{id}"
    try:
        await redis.delete(key)
    except _REDIS_ERRORS as e:
        logger.warning("Cache invalidate failed: prefix={} id={} error={}", prefix, id, e)
