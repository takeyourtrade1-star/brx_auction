"""
Rate limiting: per-IP limits shared across instances via Redis (async, non-blocking).
When TRUSTED_PROXY is True, uses X-Forwarded-For (real client IP behind proxy); value is validated to look like an IP.
When False, uses direct client IP only to avoid spoofing.

Uses the app's shared async Redis client so the event loop is never blocked.
If Redis is unavailable: RATE_LIMIT_FAIL_CLOSED=True -> 503; False -> fail open (no limit).
"""
import re
import time
from typing import Annotated

from fastapi import Depends, HTTPException, status
from loguru import logger
from starlette.requests import Request

from app.core.config import get_settings
from app.infrastructure.redis_client import get_redis_optional

# Redis key prefix; TTL (seconds) for the counter key so it expires after 2 minutes.
RATE_LIMIT_KEY_PREFIX = "ebartex:ratelimit"
RATE_LIMIT_KEY_TTL = 120

# Basic IP-like pattern to reject obviously spoofed X-Forwarded-For (e.g. long strings, scripts).
_IPV4_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
_IPV6_RE = re.compile(r"^\[?[0-9a-fA-F:.]+\]?$")


def get_request(request: Request) -> Request:
    """Dependency that provides Request. Used by rate_limit dependency to get client IP."""
    return request


def _looks_like_ip(value: str) -> bool:
    """True if value looks like an IPv4 or IPv6 address (reject spoofed non-IP content)."""
    if not value or len(value) > 45:
        return False
    return bool(_IPV4_RE.match(value) or _IPV6_RE.match(value))


def _client_ip(request: Request) -> str:
    """IP for rate limit: X-Forwarded-For only when behind a trusted proxy and value looks like an IP, else direct client IP."""
    settings = get_settings()
    if settings.TRUSTED_PROXY:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            leftmost = forwarded.split(",")[0].strip() or ""
            if _looks_like_ip(leftmost):
                return leftmost
            # Invalid or spoofed-looking value: fall back to direct client
            logger.debug("X-Forwarded-For leftmost value does not look like IP, using direct client")
    if request.client:
        return request.client.host or "0.0.0.0"
    return "0.0.0.0"


async def _check_rate_limit(request: Request, requests_per_minute: int) -> None:
    """
    Increment per-IP counter for current minute in Redis; raise 429 if over limit.
    Uses fixed 1-minute window. If Redis unavailable: fail-closed (503) or fail-open per config.
    requests_per_minute <= 0 is treated as "reject all" to avoid accidental DoS (no limit).
    """
    if requests_per_minute <= 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )
    redis = get_redis_optional()
    if not redis:
        settings = get_settings()
        if settings.RATE_LIMIT_FAIL_CLOSED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rate limiting temporarily unavailable",
            )
        return
    ip = _client_ip(request)
    window = int(time.time()) // 60
    key = f"{RATE_LIMIT_KEY_PREFIX}:{ip}:{window}"
    try:
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, RATE_LIMIT_KEY_TTL)
        results = await pipe.execute()
        count = results[0]
        if count > requests_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )
    except HTTPException:
        raise
    except Exception as e:
        # Redis error: fail-closed or fail-open per config
        logger.warning("Rate limit check failed (Redis): {}", e)
        settings = get_settings()
        if settings.RATE_LIMIT_FAIL_CLOSED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rate limiting temporarily unavailable",
            )


def rate_limit(requests_per_minute: int):
    """
    Dependency factory: returns a callable for Depends() that enforces requests_per_minute per IP per minute.
    Use in route as: Depends(rate_limit(60)).
    """
    async def _dep(request: Annotated[Request, Depends(get_request)]) -> None:
        await _check_rate_limit(request, requests_per_minute)

    return _dep
