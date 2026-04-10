"""
Auction repository: async CRUD and list with optional filter. Uses AsyncSession.
"""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.auction import Auction


def _auction_list_where(stmt, q: Optional[str], status: Optional[str]):
    """Apply optional filters for list/count. Reused so count and select stay in sync."""
    if status:
        stmt = stmt.where(Auction.status == status)
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(Auction.title.ilike(term), Auction.description.ilike(term))
        )
    return stmt


class AuctionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: dict[str, Any]) -> Auction:
        auction = Auction(
            title=data["title"],
            description=data.get("description", ""),
            starting_price=float(data["starting_price"]),
            current_price=float(data.get("current_price", data["starting_price"])),
            reserve_price=float(data["reserve_price"]) if data.get("reserve_price") is not None else None,
            start_time=data["start_time"],
            end_time=data["end_time"],
            status=data.get("status", "DRAFT"),
            highest_bidder_id=data.get("highest_bidder_id"),
            created_by_user_id=data.get("created_by_user_id"),
            product_id=data.get("product_id"),
            image_front=data.get("image_front"),
            image_back=data.get("image_back"),
            video_url=data.get("video_url"),
            buy_now_enabled=bool(data.get("buy_now_enabled", False)),
            buy_now_price=float(data["buy_now_price"]) if data.get("buy_now_price") is not None else None,
            buy_now_url=data.get("buy_now_url"),
        )
        self._session.add(auction)
        await self._session.flush()
        await self._session.refresh(auction)
        return auction

    async def find_by_id(self, id: int) -> Optional[Auction]:
        result = await self._session.execute(select(Auction).where(Auction.id == id))
        return result.scalar_one_or_none()

    async def find_by_id_for_update(self, id: int) -> Optional[Auction]:
        """
        Load auction by id with SELECT ... FOR UPDATE.
        Call only inside a transaction; holds row lock until commit/rollback.
        Use for place_bid to avoid race conditions (only one bid per auction at a time).
        """
        result = await self._session.execute(
            select(Auction).where(Auction.id == id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def find_all(
        self,
        *,
        q: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Auction], int]:
        """List auctions with filters; returns (items, total_count). Single query with COUNT(*) OVER() to avoid two round-trips."""
        max_offset = get_settings().MAX_PAGINATION_OFFSET
        offset = min(offset, max_offset)

        total_expr = func.count(Auction.id).over().label("_total")
        stmt = select(Auction, total_expr)
        stmt = _auction_list_where(stmt, q, status)
        stmt = stmt.order_by(Auction.end_time.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        rows = result.all()
        total = int(rows[0][1]) if rows else 0
        auctions = [row[0] for row in rows]
        return auctions, total

    async def update(self, auction: Auction) -> Auction:
        await self._session.flush()
        await self._session.refresh(auction)
        return auction

    async def close_expired(self) -> int:
        """Set status to CLOSED for ACTIVE auctions past end_time. Returns count."""
        from datetime import timezone
        now = datetime.now(timezone.utc)
        stmt = (
            update(Auction)
            .where(Auction.status == "ACTIVE", Auction.end_time < now)
            .values(status="CLOSED")
        )
        result = await self._session.execute(stmt)
        return result.rowcount or 0