"""
FastAPI application entry point.
CORS, middleware, routers, global exception handler.
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.api import auctions_router, bids_router, me_router, products_router
from app.core.config import get_settings
from app.infrastructure.database import init_db, close_db, check_db_connected
from app.infrastructure.http_client import init_http_client, close_http_client
from app.infrastructure.redis_client import init_redis, close_redis, check_redis_connected
from app.utils.error_handlers import base_exception_handler, global_exception_handler
from app.utils.request_id import request_id_middleware

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load config, connect DB, Redis and shared HTTP client. Shutdown: close connections."""
    logger.info("Starting up: loading config and connections")
    from app.core.security import load_public_key, shutdown_jwt_executor, get_jwt_executor
    # Load JWT key in dedicated JWT executor to avoid blocking event loop and default executor
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(get_jwt_executor(), load_public_key)
    init_http_client()
    await init_db()
    await init_redis()
    yield
    logger.info("Shutting down: closing connections")
    shutdown_jwt_executor()
    await close_http_client()
    await close_db()
    await close_redis()


app = FastAPI(
    title="Ebartex Marketplace API",
    description="Backend marketplace (auctions, bids, products, sync)",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENABLE_OPENAPI_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_OPENAPI_DOCS else None,
)

# CORS: only allowed origins and headers (no wildcard to reduce surface with credentials)
CORS_ALLOW_HEADERS = ["Authorization", "Content-Type", "Accept", "X-Request-ID"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=CORS_ALLOW_HEADERS,
)

# Request ID for tracing (e.g. CloudWatch)
app.middleware("http")(request_id_middleware)

# Security headers middleware (HSTS, X-Content-Type-Options)
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Exception handlers: Exception first (more specific), then BaseException for the rest
app.add_exception_handler(Exception, global_exception_handler)
app.add_exception_handler(BaseException, base_exception_handler)

# Routers
app.include_router(me_router, tags=["auth"])
app.include_router(auctions_router, prefix="/auctions", tags=["auctions"])
app.include_router(bids_router, prefix="/auctions", tags=["bids"])
app.include_router(products_router, prefix="/products", tags=["products"])


@app.get("/")
async def root() -> dict:
    """Health check root."""
    return {"status": "ok", "service": "ebartex-marketplace"}


@app.get("/health")
async def health():
    """
    Health check for load balancer. Verifies DB and Redis; returns 503 if required dependency is down.
    """
    db_ok = await check_db_connected()
    redis_ok = await check_redis_connected()
    if not db_ok or not redis_ok:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "database": "ok" if db_ok else "down",
                "redis": "ok" if redis_ok else "down",
            },
        )
    return {"status": "ok", "database": "ok", "redis": "ok"}
