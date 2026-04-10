"""
Standalone worker: consume reindex requests from Redis and call BRX_Search reindex.
Run with: python -m worker_reindex (or python worker_reindex.py)
Requires REDIS_URL and SEARCH_* env vars.
"""
import asyncio
import sys

# Ensure app is on path
sys.path.insert(0, ".")

import httpx

from app.infrastructure.http_client import init_http_client, close_http_client
from app.infrastructure.redis_client import init_redis, close_redis, get_redis_optional
from app.services.reindex_queue import consume_reindex_queue, enqueue_reindex
from app.infrastructure.search_client import trigger_reindex
from loguru import logger

# Recoverable errors: backoff and retry. Other exceptions (e.g. programming errors) are re-raised.
try:
    import redis.exceptions as _rex
    _WORKER_RECOVERABLE = (httpx.HTTPError, OSError, _rex.RedisError, _rex.ConnectionError, _rex.TimeoutError)
except ImportError:
    _WORKER_RECOVERABLE = (httpx.HTTPError, OSError)


async def run_once() -> tuple[bool, bool]:
    """
    Process one reindex request from queue.
    Returns (processed, success): processed=True if a message was consumed, success=True if trigger succeeded.
    On trigger failure the message is re-queued (RPUSH) so it can be retried after other items.
    """
    reason = await consume_reindex_queue()
    if reason is None:
        return False, True
    logger.info("Processing reindex request", reason=reason)
    ok = await trigger_reindex()
    if not ok:
        logger.warning("Reindex trigger failed; re-queuing message for retry")
        await enqueue_reindex(reason)
        return True, False
    return True, True


async def main() -> None:
    logger.info("Reindex worker starting")
    init_http_client()
    await init_redis()
    if get_redis_optional() is None:
        logger.error("Redis connection failed; worker cannot run")
        sys.exit(1)
    delay_sec = 5.0
    max_delay_sec = 300.0
    try:
        while True:
            try:
                processed, success = await run_once()
                if success:
                    delay_sec = 5.0  # reset backoff on success
                elif processed:
                    # Trigger failed but message re-queued; back off to avoid tight loop
                    await asyncio.sleep(delay_sec)
                    delay_sec = min(delay_sec * 2, max_delay_sec)
                # No sleep when queue empty: consume_reindex_queue() already blocks with short timeout.
            except asyncio.CancelledError:
                break
            except _WORKER_RECOVERABLE as e:
                logger.warning("Worker loop recoverable error (backoff): {}", e)
                await asyncio.sleep(delay_sec)
                delay_sec = min(delay_sec * 2, max_delay_sec)
            except Exception as e:
                logger.exception("Worker loop unexpected error (stopping): {}", e)
                raise
    finally:
        await close_http_client()
        await close_redis()
    logger.info("Reindex worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
