"""
Bid endpoints: GET /auctions/:id/bids (paginated list), GET /auctions/:id/minimum-bid (next min bid),
POST /auctions/:id/bids (place bid). Rate limited.
User identity is taken from JWT (Bearer) only for POST. BidCreate has no userId field;
do not read user from body to avoid UUID(body.userId) and unclear/invalid-ID errors.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.config import get_settings
from app.core.dependencies import get_bidding_service, get_current_user_id
from app.core.rate_limit import rate_limit
from app.schemas.bid import BidCreate
from app.services.bidding_service import BiddingService

router = APIRouter()
settings = get_settings()


@router.get(
    "/{auction_id:int}/bids",
    response_model=dict,
    description="List bids for an auction (paginated, chronological). Public. 404 if auction does not exist.",
)
async def list_bids_for_auction(
    auction_id: int,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    service: BiddingService = Depends(get_bidding_service),
    _rate_limit: None = Depends(rate_limit(settings.RATE_LIMIT_SEARCH)),
):
    offset = min(offset, settings.MAX_PAGINATION_OFFSET)
    items, total = await service.list_bids_for_auction(
        auction_id, limit=limit, offset=offset
    )
    return {
        "success": True,
        "data": items,
        "limit": limit,
        "offset": offset,
        "total": total,
    }


@router.get(
    "/{auction_id:int}/minimum-bid",
    response_model=dict,
    description="Minimum next bid (current price + increment). Public. Same rule as POST bids. 404 if auction does not exist.",
)
async def get_minimum_next_bid(
    auction_id: int,
    service: BiddingService = Depends(get_bidding_service),
    _rate_limit: None = Depends(rate_limit(settings.RATE_LIMIT_SEARCH)),
):
    data = await service.get_minimum_next_bid(auction_id)
    return {"success": True, "data": data}


@router.post(
    "/{auction_id:int}/bids",
    response_model=dict,
    status_code=201,
    description="Place a bid on an auction. Min increment and 5-min extension apply. Requires Bearer token.",
)
async def place_bid(
    auction_id: int,
    body: BidCreate,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    service: BiddingService = Depends(get_bidding_service),
    _rate_limit: None = Depends(rate_limit(settings.RATE_LIMIT_DEFAULT)),
):
    result = await service.place_bid(
        auction_id=auction_id,
        user_id=user_id,
        amount=body.amount,
        max_amount=body.maxAmount,
    )
    return {"success": True, "data": result}
