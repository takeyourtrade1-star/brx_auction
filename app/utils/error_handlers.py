"""
Global exception handlers: map AppError to JSON; generic 500 for rest.
BaseException (e.g. KeyboardInterrupt, SystemExit) re-raised so process/runtime behave correctly.
No stack trace or SQL to client (information disclosure prevention).
"""
from typing import Any

from fastapi import Request, Response
from loguru import logger

from app.utils.exceptions import AppError


# Subclasses of BaseException that are not Exception: never swallow these.
_RE_RAISE_BASE_EXCEPTIONS = (KeyboardInterrupt, SystemExit, GeneratorExit)


async def base_exception_handler(request: Request, exc: BaseException) -> Response:
    """
    Handle BaseException that are not Exception (e.g. KeyboardInterrupt, SystemExit).
    Re-raise so the process can exit or the runtime handles the interrupt; otherwise return 500 JSON.
    """
    if isinstance(exc, _RE_RAISE_BASE_EXCEPTIONS):
        raise exc
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "BaseException (not Exception)",
        extra={"request_id": request_id, "path": request.url.path, "type": type(exc).__name__},
        exc_info=True,
    )
    return Response(
        content=__json_content("An unexpected error occurred.", "INTERNAL_ERROR"),
        status_code=500,
        media_type="application/json",
    )


async def global_exception_handler(request: Request, exc: Exception) -> Response:
    """Centralized handler: AppError -> JSON with code/detail; other -> 500 generic."""
    request_id = getattr(request.state, "request_id", None)
    if isinstance(exc, AppError):
        return Response(
            content=__json_content(exc.message, exc.code, exc.detail),
            status_code=exc.status_code,
            media_type="application/json",
        )
    logger.error(
        "Unhandled exception",
        extra={"request_id": request_id, "path": request.url.path},
        exc_info=True,
    )
    return Response(
        content=__json_content("An unexpected error occurred.", "INTERNAL_ERROR"),
        status_code=500,
        media_type="application/json",
    )


def __json_content(detail: str, code: str, extra: dict[str, Any] | None = None) -> str:
    import json
    body: dict[str, Any] = {"detail": detail, "code": code}
    if extra:
        body.update(extra)
    return json.dumps(body)
