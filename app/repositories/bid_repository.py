"""
Bid repository: async create and list by auction. Uses AsyncSession.
"""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bid import Bid


class BidRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: dict) -> Bid:
        bid = Bid(
            auction_id=data["auction_id"],
            user_id=data["user_id"],
            amount=float(data["amount"]),
            max_amount=float(data["max_amount"]) if data.get("max_amount") is not None else None,
        )
        self._session.add(bid)
        await self._session.flush()
        await self._session.refresh(bid)
        return bid

    async def find_by_auction_id(self, auction_id: int, limit: int | None = None) -> list[Bid]:
        """Bids for auction, chronological order. If limit is set, returns the most recent `limit` bids (still in chronological order)."""
        stmt = (
            select(Bid).where(Bid.auction_id == auction_id).order_by(Bid.created_at.asc())
        )
        if limit is not None:
            # Subquery: last N by created_at desc, then order asc for response
            subq = (
                select(Bid.id).where(Bid.auction_id == auction_id).order_by(Bid.created_at.desc()).limit(limit)
            )
            stmt = select(Bid).where(Bid.id.in_(subq)).order_by(Bid.created_at.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_auction_id(self, auction_id: int) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Bid).where(Bid.auction_id == auction_id)
        )
        return int(result.scalar_one())

    async def find_by_auction_id_paginated(
        self, auction_id: int, *, limit: int, offset: int
    ) -> list[Bid]:
        """Bids for auction in chronological order (oldest first), with SQL limit/offset."""
        stmt = (
            select(Bid)
            .where(Bid.auction_id == auction_id)
            .order_by(Bid.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_leader_max_amount(self, auction_id: int, user_id: UUID) -> float | None:
        """Max max_amount for the given bidder on this auction (single query, no full list)."""
        result = await self._session.execute(
            select(func.max(Bid.max_amount)).where(
                Bid.auction_id == auction_id,
                Bid.user_id == user_id,
            )
        )
        value = result.scalar_one()
        return float(value) if value is not None else None

    async def find_by_id(self, id: int) -> Bid | None:
        result = await self._session.execute(select(Bid).where(Bid.id == id))
        return result.scalar_one_or_none()
