"""
Middleware to add request_id to each request for tracing (e.g. CloudWatch).
X-Request-ID from the client is validated (length + safe charset) to avoid log injection
and oversized values; invalid or missing header is replaced with a generated UUID.
"""
import re
import uuid

from starlette.requests import Request
from starlette.responses import Response

# Safe for logs and tracing: alphanumeric, hyphen, underscore. Max length to avoid huge payloads.
REQUEST_ID_MAX_LEN = 128
_REQUEST_ID_PATTERN = re.compile(rf"^[a-zA-Z0-9_-]{{1,{REQUEST_ID_MAX_LEN}}}$")


def _valid_request_id(value: str | None) -> bool:
    """True if value is non-empty, within length, and only allowed characters."""
    if not value or not value.strip():
        return False
    if len(value) > REQUEST_ID_MAX_LEN:
        return False
    return _REQUEST_ID_PATTERN.match(value.strip()) is not None


def _get_or_create_request_id(request: Request) -> str:
    """Return validated X-Request-ID from header or a new UUID. Prevents log injection and oversized IDs."""
    raw = request.headers.get("X-Request-ID")
    if _valid_request_id(raw):
        return (raw or "").strip()
    return str(uuid.uuid4())


async def request_id_middleware(request: Request, call_next) -> Response:
    """Set request_id on request.state and on response header. Client value is validated."""
    request_id = _get_or_create_request_id(request)
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
