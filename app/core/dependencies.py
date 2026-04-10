"""
FastAPI dependencies: auth (JWT) and service factories.
- Auth: get_current_user_id, get_current_user_payload (401 if token missing/invalid).
- Services: single place to build AuctionService, ProductService, BiddingService (no duplicate factories in routers).
"""
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, PyJWTError
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.infrastructure.auth_client import get_auth_me
from app.infrastructure.database import get_db
from app.repositories.auction_repository import AuctionRepository
from app.repositories.bid_repository import BidRepository
from app.repositories.product_repository import ProductRepository
from app.services.auction_service import AuctionService
from app.services.bidding_service import BiddingService
from app.services.product_service import ProductService

security = HTTPBearer(auto_error=False)


def _jwt_error_detail(exc: PyJWTError) -> str:
    """User-facing message; never expose str(exc) or exception internals."""
    if isinstance(exc, ExpiredSignatureError):
        return "Token expired"
    return "Invalid token"


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> UUID:
    """Extract and validate JWT; return user id (sub). Raises 401 if missing/invalid."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = await decode_access_token(credentials.credentials)
    except PyJWTError as exc:
        logger.debug("JWT validation failed: {}", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_jwt_error_detail(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return UUID(str(sub))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user id in token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_payload(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> dict:
    """Extract and validate JWT; return full payload (sub, email, etc.). Raises 401 if missing/invalid."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return await decode_access_token(credentials.credentials)
    except PyJWTError as exc:
        logger.debug("JWT validation failed: {}", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_jwt_error_detail(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_id_and_piva(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> tuple[UUID, bool]:
    """Extract user id from JWT and whether user has P.IVA (from Auth /me when AUTH_BASE_URL set). Raises 401 if missing/invalid."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = await decode_access_token(credentials.credentials)
    except PyJWTError as exc:
        logger.debug("JWT validation failed: {}", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_jwt_error_detail(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = UUID(str(sub))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user id in token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    has_piva = False
    settings = get_settings()
    if settings.AUTH_BASE_URL:
        result = await get_auth_me(credentials.credentials)
        if result and result.success and result.payload:
            has_piva = bool(result.payload.get("piva"))
    return (user_id, has_piva)


# --- Service factories (single place; used by auctions, products, bids routers) ---


def get_auction_service(session: Annotated[AsyncSession, Depends(get_db)]) -> AuctionService:
    return AuctionService(
        AuctionRepository(session),
        ProductRepository(session),
    )


def get_product_service(session: Annotated[AsyncSession, Depends(get_db)]) -> ProductService:
    return ProductService(ProductRepository(session))


def get_bidding_service(session: Annotated[AsyncSession, Depends(get_db)]) -> BiddingService:
    return BiddingService(AuctionRepository(session), BidRepository(session))
