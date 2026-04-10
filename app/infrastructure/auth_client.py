"""
Optional HTTP client for Auth service (e.g. GET /api/auth/me for user info/role).
Uses httpx async. Timeout and errors are configurable and differentiated.
Circuit breaker: after N consecutive failures, stop calling Auth for cooldown to avoid cascading timeouts.
State is shared across workers via Redis when available; falls back to in-process state if Redis is down.
r.json() is run off the event loop to avoid blocking under high concurrency.
"""
import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Literal, Optional

import httpx
from loguru import logger

from app.core.config import get_settings
from app.infrastructure.http_client import get_http_client
from app.infrastructure.redis_client import get_redis_optional

# Redis keys for circuit breaker (shared across all app instances).
_AUTH_CIRCUIT_OPEN_KEY = "ebartex:auth:circuit:open"
_AUTH_CIRCUIT_FAILURES_KEY = "ebartex:auth:circuit:failures"
_AUTH_CIRCUIT_FAILURES_TTL = 120  # seconds; failures count expires if no activity

# Fallback in-process state when Redis is unavailable.
_auth_failures = 0
_auth_circuit_open_until: float = 0.0


@dataclass
class AuthMeResult:
    """Result of get_auth_me; allows distinguishing success, 4xx, 5xx, and network errors."""

    success: bool
    payload: Optional[dict[str, Any]] = None
    error_type: Optional[
        Literal["not_authenticated", "service_error", "network_error"]
    ] = None

    @property
    def is_not_authenticated(self) -> bool:
        return self.error_type == "not_authenticated"

    @property
    def is_service_error(self) -> bool:
        return self.error_type == "service_error"

    @property
    def is_network_error(self) -> bool:
        return self.error_type == "network_error"


async def _auth_circuit_open(settings: Any) -> bool:
    """True if circuit is open (too many failures); cooldown elapsed allows one try (half-open). Uses Redis when available."""
    redis = get_redis_optional()
    if redis:
        try:
            if await redis.get(_AUTH_CIRCUIT_OPEN_KEY):
                return True
            raw = await redis.get(_AUTH_CIRCUIT_FAILURES_KEY)
            count = int(raw) if raw else 0
            if count >= settings.AUTH_CIRCUIT_FAILURE_THRESHOLD:
                await redis.setex(
                    _AUTH_CIRCUIT_OPEN_KEY,
                    int(settings.AUTH_CIRCUIT_COOLDOWN_SECONDS),
                    "1",
                )
                await redis.delete(_AUTH_CIRCUIT_FAILURES_KEY)
                logger.warning(
                    "Auth circuit breaker open for {:.0f}s after {} failures (Redis)",
                    settings.AUTH_CIRCUIT_COOLDOWN_SECONDS,
                    count,
                )
                return True
            return False
        except Exception as e:
            logger.debug("Auth circuit Redis check failed, using in-memory: {}", e)
    # In-memory fallback
    global _auth_failures, _auth_circuit_open_until
    if _auth_failures < settings.AUTH_CIRCUIT_FAILURE_THRESHOLD:
        return False
    if time.monotonic() < _auth_circuit_open_until:
        return True
    _auth_failures = 0
    return False


async def _auth_record_success() -> None:
    redis = get_redis_optional()
    if redis:
        try:
            await redis.delete(_AUTH_CIRCUIT_FAILURES_KEY)
            await redis.delete(_AUTH_CIRCUIT_OPEN_KEY)
            return
        except Exception:
            pass
    global _auth_failures
    _auth_failures = 0


async def _auth_record_failure(settings: Any) -> None:
    redis = get_redis_optional()
    if redis:
        try:
            pipe = redis.pipeline()
            pipe.incr(_AUTH_CIRCUIT_FAILURES_KEY)
            pipe.expire(_AUTH_CIRCUIT_FAILURES_KEY, _AUTH_CIRCUIT_FAILURES_TTL)
            results = await pipe.execute()
            count = results[0]
            if count >= settings.AUTH_CIRCUIT_FAILURE_THRESHOLD:
                await redis.setex(
                    _AUTH_CIRCUIT_OPEN_KEY,
                    int(settings.AUTH_CIRCUIT_COOLDOWN_SECONDS),
                    "1",
                )
                await redis.delete(_AUTH_CIRCUIT_FAILURES_KEY)
                logger.warning(
                    "Auth circuit breaker open for {:.0f}s after {} failures (Redis)",
                    settings.AUTH_CIRCUIT_COOLDOWN_SECONDS,
                    count,
                )
            return
        except Exception as e:
            logger.debug("Auth circuit Redis record failure failed, using in-memory: {}", e)
    global _auth_failures, _auth_circuit_open_until
    _auth_failures += 1
    if _auth_failures >= settings.AUTH_CIRCUIT_FAILURE_THRESHOLD:
        _auth_circuit_open_until = time.monotonic() + settings.AUTH_CIRCUIT_COOLDOWN_SECONDS
        logger.warning(
            "Auth circuit breaker open for {:.0f}s after {} failures",
            settings.AUTH_CIRCUIT_COOLDOWN_SECONDS,
            _auth_failures,
        )


async def get_auth_me(bearer_token: str) -> Optional[AuthMeResult]:
    """
    Call GET /api/auth/me with Bearer token.
    Returns None only when AUTH_BASE_URL is empty (feature disabled).
    When circuit breaker is open, returns service_error without calling Auth.
    Otherwise returns AuthMeResult so callers can distinguish:
    - success + payload (200)
    - not_authenticated (4xx)
    - service_error (5xx, invalid JSON, circuit open) — logged
    - network_error (timeout, connection, transport) — logged with distinct messages.
    Only known httpx/JSON errors are caught; any other exception propagates.
    """
    settings = get_settings()
    base = settings.AUTH_BASE_URL
    if not base:
        return None
    if await _auth_circuit_open(settings):
        return AuthMeResult(success=False, error_type="service_error")
    url = f"{base.rstrip('/')}/api/auth/me"
    timeout = settings.AUTH_TIMEOUT_SECONDS
    try:
        client = get_http_client()
        r = await client.get(
            url,
            headers={"Authorization": f"Bearer {bearer_token}"},
            timeout=timeout,
        )
    except httpx.TimeoutException as exc:
        logger.warning(
            "Auth service timeout after {}s: {}",
            timeout,
            type(exc).__name__,
            exc_info=False,
        )
        await _auth_record_failure(settings)
        return AuthMeResult(success=False, error_type="network_error")
    except httpx.ConnectError as exc:
        logger.warning(
            "Auth service connection failed (unreachable): {}",
            type(exc).__name__,
            exc_info=False,
        )
        await _auth_record_failure(settings)
        return AuthMeResult(success=False, error_type="network_error")
    except httpx.RequestError as exc:
        logger.warning(
            "Auth service request error (transport): {}",
            type(exc).__name__,
            exc_info=False,
        )
        await _auth_record_failure(settings)
        return AuthMeResult(success=False, error_type="network_error")

    if r.status_code == 200:
        await _auth_record_success()
        try:
            # Parse JSON off event loop to avoid blocking under high concurrency (sync r.json() can block).
            payload = await asyncio.to_thread(r.json)
            return AuthMeResult(success=True, payload=payload)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "Auth service invalid JSON response: {}",
                exc,
                exc_info=False,
            )
            await _auth_record_failure(settings)
            return AuthMeResult(success=False, error_type="service_error")

    if 400 <= r.status_code < 500:
        await _auth_record_success()  # 4xx is not a server failure
        return AuthMeResult(
            success=False,
            error_type="not_authenticated",
        )
    # 5xx or other
    logger.warning(
        "Auth service returned {}",
        r.status_code,
    )
    await _auth_record_failure(settings)
    return AuthMeResult(
        success=False,
        error_type="service_error",
    )
