"""
Bidding business logic: place bid, min increment, proxy bidding, 5-min extension.
All user identity in this module is UUID; no string conversion for comparisons or storage.
Accepts Decimal for amount/max_amount from API; converts to float at repository boundary (DB uses float).
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from app.core.cache import invalidate_cached
from app.core.config import get_settings
from app.models.bid import Bid
from app.repositories.auction_repository import AuctionRepository
from app.repositories.bid_repository import BidRepository
from app.services.auction_domain import auction_to_dict, with_current_status, _now, _is_before
from app.utils.exceptions import (
    AuctionNotFoundError,
    AuctionNotActiveError,
    BidTooLowError,
    BidAboveMaxError,
)

MIN_REMAINING_MINUTES_AFTER_BID = 5


def _bid_create_data(
    auction_id: int,
    user_id: UUID,
    amount: float,
    max_amount: float | None,
) -> dict[str, Any]:
    """Single place for bid create payload; ensures user_id is always UUID."""
    return {
        "auction_id": auction_id,
        "user_id": user_id,
        "amount": amount,
        "max_amount": max_amount,
    }


def _bid_to_api_dict(b: Bid) -> dict[str, Any]:
    return {
        "id": b.id,
        "auction_id": b.auction_id,
        "user_id": b.user_id,
        "amount": b.amount,
        "max_amount": b.max_amount,
        "created_at": b.created_at,
    }


def get_min_increment(current_price: float) -> float:
    """Price < 100 -> 1; price >= 100 -> 2.5% rounded to 2 decimals. Uses Decimal for percentage to avoid float drift."""
    p = Decimal(str(current_price))
    if p < 100:
        return 1.0
    return float((p * Decimal("0.025")).quantize(Decimal("0.01")))


class BiddingService:
    def __init__(
        self,
        auction_repo: AuctionRepository,
        bid_repo: BidRepository,
    ) -> None:
        self._auction_repo = auction_repo
        self._bid_repo = bid_repo

    async def list_bids_for_auction(
        self, auction_id: int, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        """List bids for an auction (paginated, chronological). Raises AuctionNotFoundError if auction missing."""
        auction = await self._auction_repo.find_by_id(auction_id)
        if auction is None:
            raise AuctionNotFoundError()
        total = await self._bid_repo.count_by_auction_id(auction_id)
        rows = await self._bid_repo.find_by_auction_id_paginated(
            auction_id, limit=limit, offset=offset
        )
        items = [_bid_to_api_dict(b) for b in rows]
        return items, total

    async def get_minimum_next_bid(self, auction_id: int) -> dict[str, Any]:
        """
        Current price plus required increment (same rule as place_bid). Read-only; 404 if auction missing.
        """
        auction = await self._auction_repo.find_by_id(auction_id)
        if auction is None:
            raise AuctionNotFoundError()
        cp = float(auction.current_price)
        inc = get_min_increment(cp)
        return {
            "auction_id": auction_id,
            "current_price": cp,
            "min_increment": inc,
            "minimum_next_bid": cp + inc,
        }

    async def place_bid(
        self,
        auction_id: int,
        user_id: UUID,
        amount: Decimal | float,
        max_amount: Optional[Decimal | float] = None,
    ) -> dict[str, Any]:
        """
        Place a bid (or proxy bids) and update auction. Must be called within a single
        DB transaction: the auction row is locked with SELECT ... FOR UPDATE so
        concurrent requests for the same auction are serialized and cannot both pass
        min_required or create inconsistent highest_bidder/current_price.
        """
        auction = await self._auction_repo.find_by_id_for_update(auction_id)
        if not auction:
            raise AuctionNotFoundError()
        with_status = with_current_status(auction_to_dict(auction))
        if with_status["status"] != "ACTIVE":
            raise AuctionNotActiveError()
        now_dt = _now()
        end_dt = auction.end_time
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        if not _is_before(now_dt, end_dt):
            raise AuctionNotActiveError("Auction has ended.")

        _amount = float(amount) if isinstance(amount, Decimal) else amount
        _max_amount = float(max_amount) if isinstance(max_amount, Decimal) else max_amount
        min_required = auction.current_price + get_min_increment(auction.current_price)
        if _amount < min_required:
            raise BidTooLowError(f"Minimum bid is {min_required}.")
        if _max_amount is not None and _amount > _max_amount:
            raise BidAboveMaxError("In a single bid, amount cannot be greater than maxAmount.")

        # Current leader (UUID | None); all bid create/update use UUID for user identity.
        previous_leader_id: UUID | None = auction.highest_bidder_id
        previous_leader_max: float | None = (
            await self._bid_repo.get_leader_max_amount(auction_id, previous_leader_id)
            if previous_leader_id is not None
            else None
        )

        min_to_beat_new = _amount + get_min_increment(_amount)
        previous_leader_can_beat = previous_leader_max is not None and previous_leader_max >= min_to_beat_new
        min_for_new_to_win = (
            previous_leader_max + get_min_increment(previous_leader_max)
            if previous_leader_max is not None
            else None
        )
        new_bidder_wins_by_proxy = (
            previous_leader_id is not None
            and _max_amount is not None
            and min_for_new_to_win is not None
            and _max_amount >= min_for_new_to_win
        )

        if new_bidder_wins_by_proxy:
            await self._bid_repo.create(
                _bid_create_data(auction_id, user_id, min_for_new_to_win, _max_amount)
            )
            auction.current_price = min_for_new_to_win
            auction.highest_bidder_id = user_id
        elif previous_leader_can_beat:
            if previous_leader_id is None or previous_leader_max is None:
                raise RuntimeError(
                    "Invariant violation: previous_leader_can_beat requires previous_leader_id and previous_leader_max"
                )
            await self._bid_repo.create(
                _bid_create_data(auction_id, previous_leader_id, min_to_beat_new, previous_leader_max)
            )
            await self._bid_repo.create(
                _bid_create_data(auction_id, user_id, _amount, _max_amount)
            )
            auction.current_price = min_to_beat_new
            auction.highest_bidder_id = previous_leader_id
        else:
            await self._bid_repo.create(
                _bid_create_data(auction_id, user_id, _amount, _max_amount)
            )
            auction.current_price = _amount
            auction.highest_bidder_id = user_id

        remaining_sec = (end_dt - now_dt).total_seconds()
        if remaining_sec < MIN_REMAINING_MINUTES_AFTER_BID * 60:
            auction.end_time = now_dt + timedelta(minutes=MIN_REMAINING_MINUTES_AFTER_BID)

        await self._auction_repo.update(auction)
        await invalidate_cached("auction", auction_id)

        bids_limit = get_settings().PLACE_BID_RESPONSE_BIDS_LIMIT
        updated_bids = await self._bid_repo.find_by_auction_id(auction_id, limit=bids_limit)
        return {
            "auction": with_current_status(auction_to_dict(auction)),
            "bids": [_bid_to_api_dict(b) for b in updated_bids],
        }
