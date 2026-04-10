"""
Auction endpoints: create, list (paginated), get by id, PATCH (buy-it-now/video). Rate limited.
Create and PATCH require authentication (Bearer). P.IVA sellers can add video and buy-it-now.
"""
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.config import get_settings
from app.core.dependencies import get_auction_service, get_current_user_id_and_piva
from app.core.rate_limit import rate_limit
from app.schemas.auction import AuctionCreate, AuctionUpdate, AuctionResponse, AuctionListResponse
from app.services.auction_service import AuctionService

router = APIRouter()
settings = get_settings()


@router.post(
    "/",
    response_model=dict,
    status_code=201,
    description="Create a new auction. Requires image_front/image_back (or match product). P.IVA: optional video_url, buy_now.",
)
async def create_auction(
    body: AuctionCreate,
    user_id_and_piva: Annotated[tuple[UUID, bool], Depends(get_current_user_id_and_piva)],
    service: AuctionService = Depends(get_auction_service),
    _rate_limit: None = Depends(rate_limit(settings.RATE_LIMIT_DEFAULT)),
):
    user_id, has_piva = user_id_and_piva
    data = body.model_dump(exclude_none=False)
    data["created_by_user_id"] = user_id
    data["has_piva"] = has_piva
    auction = await service.create_auction(data)
    return {"success": True, "data": auction}


@router.get(
    "/",
    response_model=dict,
    description="List auctions with optional search (q) and pagination.",
)
async def list_auctions(
    q: Optional[str] = Query(None, max_length=200),
    status: Optional[str] = Query(None, description="Filter by status (e.g. ACTIVE, CLOSED, DRAFT)"),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    service: AuctionService = Depends(get_auction_service),
    _rate_limit: None = Depends(rate_limit(settings.RATE_LIMIT_SEARCH)),
):
    offset = min(offset, settings.MAX_PAGINATION_OFFSET)
    items, total = await service.list_auctions(q=q, status=status, limit=limit, offset=offset)
    return {
        "success": True,
        "data": items,
        "limit": limit,
        "offset": offset,
        "total": total,
    }


@router.get(
    "/{auction_id:int}",
    response_model=dict,
    description="Get auction by id.",
)
async def get_auction_by_id(
    auction_id: int,
    service: AuctionService = Depends(get_auction_service),
    _rate_limit: None = Depends(rate_limit(settings.RATE_LIMIT_SEARCH)),
):
    auction = await service.get_auction_by_id(auction_id)
    return {"success": True, "data": auction}


@router.patch(
    "/{auction_id:int}",
    response_model=dict,
    description="Update auction (video_url, buy_now) while ACTIVE. Only for owner; P.IVA required for video/buy_now.",
)
async def update_auction_partial(
    auction_id: int,
    body: AuctionUpdate,
    user_id_and_piva: Annotated[tuple[UUID, bool], Depends(get_current_user_id_and_piva)],
    service: AuctionService = Depends(get_auction_service),
    _rate_limit: None = Depends(rate_limit(settings.RATE_LIMIT_DEFAULT)),
):
    user_id, has_piva = user_id_and_piva
    update_data = body.model_dump(exclude_unset=True)
    auction = await service.update_auction_partial(auction_id, user_id, update_data, has_piva)
    return {"success": True, "data": auction}
