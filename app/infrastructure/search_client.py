"""
Client for BRX_Search: trigger reindex via POST /api/admin/reindex.
Uses shared httpx async client (connection pooling). Called by Redis worker or from services.
"""
import httpx
from loguru import logger

from app.core.config import get_settings
from app.infrastructure.http_client import get_http_client

settings = get_settings()


async def trigger_reindex() -> bool:
    """
    Call BRX_Search reindex endpoint. Returns True if accepted (202) or success, False on error.
    Network/timeout/HTTP errors are logged and return False; other errors (e.g. config) are re-raised.
    """
    url = f"{settings.SEARCH_BASE_URL.rstrip('/')}/api/admin/reindex"
    headers = {"X-Admin-API-Key": settings.SEARCH_ADMIN_API_KEY}
    try:
        client = get_http_client()
        r = await client.post(url, headers=headers, timeout=30.0)
        if r.status_code in (200, 202):
            logger.info("BRX_Search reindex triggered", status=r.status_code)
            return True
        logger.warning("BRX_Search reindex failed", status=r.status_code, body=r.text[:200])
        return False
    except httpx.HTTPError as e:
        # Request/connection/timeout/response errors: recoverable, do not mask
        logger.error("BRX_Search reindex request error: {}", e)
        return False
    except Exception:
        # Config, SSL, or unexpected errors: re-raise so they are not masked as "reindex failed"
        logger.exception("BRX_Search reindex unexpected error")
        raise
