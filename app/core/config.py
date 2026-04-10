"""
Application settings from environment.
Maps exactly the env vars injected by start.sh (AWS SSM → docker-compose).
No defaults for security-sensitive variables: app crashes at startup if any is missing.

Multi-worker scaling: with N processes (e.g. Gunicorn workers), total DB connections ≈ N * (DB_POOL_SIZE + DB_MAX_OVERFLOW).
Keep total below PostgreSQL max_connections (e.g. 200). Redis pool (REDIS_MAX_CONNECTIONS) is per process; size for N workers.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root (ebartex_aste_py), so .env is found even when running from other dirs (e.g. alembic).
# .env must NOT be committed (it is in .gitignore); deploy via env vars or secret manager only.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Required (no default): injected by host / start.sh ---
    DB_USER: str = Field(..., description="PostgreSQL user")
    DB_PASS: str = Field(..., description="PostgreSQL password")
    DB_HOST: str = Field(..., description="PostgreSQL host (e.g. RDS endpoint)")
    DB_NAME: str = Field(..., description="PostgreSQL database name")
    DB_PORT: int = Field(default=5432, description="PostgreSQL port")

    MEILISEARCH_MASTER_KEY: str = Field(..., description="Meilisearch master key")
    SEARCH_ADMIN_API_KEY: str = Field(..., description="X-Admin-API-Key for reindex endpoint")
    SECRET_KEY: str = Field(..., description="Application secret key")
    # Required by start.sh; use a placeholder if encryption is not used yet (no default for security).
    FERNET_KEY: str = Field(..., description="Fernet encryption key (inject placeholder if not yet used)")
    JWT_PRIVATE_KEY: str = Field(..., description="JWT private key PEM (Auth service)")
    JWT_PUBLIC_KEY: str = Field(..., description="JWT public key PEM for token validation")

    # --- Computed: async PostgreSQL URL (never log this; use DATABASE_URL_MASKED for logs) ---
    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @computed_field
    @property
    def DATABASE_URL_MASKED(self) -> str:
        """Same as DATABASE_URL but with password redacted. Use only for logging/traces."""
        return (
            f"postgresql+asyncpg://{self.DB_USER}:***"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # --- Optional / non-sensitive (defaults allowed) ---
    DEBUG: bool = Field(default=False, description="Debug mode")
    # Explicit opt-in for OpenAPI docs (/docs, /redoc). Do not rely on DEBUG alone in production.
    ENABLE_OPENAPI_DOCS: bool = Field(
        default=False,
        description="If True, expose /docs and /redoc. Set explicitly; avoid DEBUG=true in production.",
    )
    # When True, rate limiting uses X-Forwarded-For (real client IP behind proxy). Set True only behind a trusted proxy that sets/validates this header; otherwise clients can spoof it.
    TRUSTED_PROXY: bool = Field(
        default=False,
        description="True only if behind a trusted proxy that sets X-Forwarded-For; else rate limit uses direct client IP.",
    )
    LOG_LEVEL: str = Field(default="INFO", description="Log level")
    HOST: str = Field(default="0.0.0.0", description="Bind host")
    PORT: int = Field(default=8000, description="Bind port")

    # Per-process pool; total connections ≈ N workers × (DB_POOL_SIZE + DB_MAX_OVERFLOW). Defaults stay under PG max_connections (e.g. 200) with 4 workers.
    DB_POOL_SIZE: int = Field(
        default=20,
        description="Connection pool size per process. Tune so N workers × (pool+overflow) ≤ PostgreSQL max_connections.",
    )
    DB_MAX_OVERFLOW: int = Field(
        default=30,
        description="Max overflow connections per process beyond DB_POOL_SIZE.",
    )
    DB_POOL_TIMEOUT: float = Field(
        default=30.0,
        description="Seconds to wait for a connection from the pool before raising; avoids indefinite hang under load.",
    )

    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL for cache, rate limit, reindex queue",
    )
    REDIS_MAX_CONNECTIONS: int = Field(
        default=50,
        description="Max connections in the Redis connection pool per process (cache, rate limit, reindex); for 100k+ users increase or scale workers.",
    )
    REDIS_SOCKET_CONNECT_TIMEOUT: float = Field(
        default=5.0,
        description="Redis socket connect timeout in seconds.",
    )

    JWT_ALGORITHM: str = Field(default="RS256", description="JWT algorithm")
    JWT_EXECUTOR_MAX_WORKERS: int = Field(
        default=64,
        description="Max threads in the dedicated pool for JWT verification (CPU-bound). Tune for high concurrency.",
    )
    JWT_KEY_REFRESH_SECONDS: int = Field(
        default=300,
        description="Seconds after which JWT public key is re-read from config (0 = no refresh, key loaded once).",
    )

    SEARCH_BASE_URL: str = Field(
        default="http://localhost:8001",
        description="BRX_Search / Meilisearch base URL",
    )

    AUTH_BASE_URL: str = Field(
        default="",
        description="Auth service base URL for GET /api/auth/me (user info/role). Empty = disabled.",
    )
    AUTH_TIMEOUT_SECONDS: float = Field(
        default=10.0,
        description="Timeout in seconds for GET /api/auth/me calls.",
    )
    # Circuit breaker: after this many consecutive failures, stop calling Auth for AUTH_CIRCUIT_COOLDOWN_SECONDS.
    AUTH_CIRCUIT_FAILURE_THRESHOLD: int = Field(
        default=5,
        description="Consecutive Auth failures before opening circuit.",
    )
    AUTH_CIRCUIT_COOLDOWN_SECONDS: float = Field(
        default=60.0,
        description="Seconds to keep Auth circuit open before trying again (half-open).",
    )

    # Shared HTTP client (Auth, BRX_Search): tune for high concurrency to avoid connection starvation.
    HTTP_MAX_CONNECTIONS: int = Field(
        default=200,
        description="Max connections in the shared outbound HTTP client pool.",
    )
    HTTP_KEEPALIVE_CONNECTIONS: int = Field(
        default=100,
        description="Max keepalive connections in the shared outbound HTTP client pool.",
    )
    HTTP_TIMEOUT_SECONDS: float = Field(default=30.0, description="Default timeout for outbound HTTP requests.")

    CORS_ORIGINS: str = Field(
        default="http://localhost:3000",
        description="Comma-separated allowed origins",
    )

    RATE_LIMIT_DEFAULT: int = Field(default=60, description="Default requests per minute per IP")
    RATE_LIMIT_SEARCH: int = Field(default=100, description="Search endpoint limit per minute")
    RATE_LIMIT_AUTH_LIKE: int = Field(default=5, description="Auth-like endpoints limit per minute")
    # When True, return 503 if Redis is down so rate limit is enforced (fail-closed). Default True for DoS mitigation.
    RATE_LIMIT_FAIL_CLOSED: bool = Field(
        default=True,
        description="If True, when Redis is unavailable return 503 instead of allowing requests (DoS mitigation).",
    )

    # Pagination: max offset to avoid O(offset) DB cost and DoS (PostgreSQL still scans skipped rows).
    MAX_PAGINATION_OFFSET: int = Field(
        default=10_000,
        description="Maximum allowed offset for list/search endpoints; offsets above this are clamped.",
    )
    # Max bids returned in place_bid response (avoids unbounded list for auctions with many bids).
    PLACE_BID_RESPONSE_BIDS_LIMIT: int = Field(default=50, description="Max bids returned after placing a bid.")

    REDIS_REINDEX_QUEUE: str = Field(
        default="ebartex:reindex:queue",
        description="Redis list key for reindex requests",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
