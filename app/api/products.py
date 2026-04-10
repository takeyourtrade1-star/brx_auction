"""
Product endpoints: search (paginated), get by id, create, create auction for product.
Create and create auction require authentication (Bearer).
"""
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.config import get_settings
from app.core.dependencies import get_auction_service, get_product_service, get_current_user_id, get_current_user_id_and_piva
from app.core.rate_limit import rate_limit
from app.schemas.product import ProductCreate
from app.schemas.auction import AuctionCreate
from app.services.auction_service import AuctionService
from app.services.product_service import ProductService
from app.utils.exceptions import ProductNotFoundError

router = APIRouter()
settings = get_settings()


@router.get(
    "/",
    response_model=dict,
    description="Search products with optional q; pagination.",
)
async def search_products(
    q: Optional[str] = Query(None, max_length=200),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    service: ProductService = Depends(get_product_service),
    _rate_limit: None = Depends(rate_limit(settings.RATE_LIMIT_SEARCH)),
):
    offset = min(offset, settings.MAX_PAGINATION_OFFSET)
    items, total = await service.search_products(q=q, limit=limit, offset=offset)
    return {
        "success": True,
        "data": items,
        "limit": limit,
        "offset": offset,
        "total": total,
    }


@router.get(
    "/{product_id:int}",
    response_model=dict,
    description="Get product by id.",
)
async def get_product_by_id(
    product_id: int,
    service: Annotated[ProductService, Depends(get_product_service)],
    _rate_limit: None = Depends(rate_limit(settings.RATE_LIMIT_SEARCH)),
):
    product = await service.get_product_by_id(product_id)
    if not product:
        raise ProductNotFoundError()
    return {"success": True, "data": product}


@router.post(
    "/",
    response_model=dict,
    status_code=201,
    description="Create a product. Requires Bearer token.",
)
async def create_product(
    body: ProductCreate,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    service: ProductService = Depends(get_product_service),
    _rate_limit: None = Depends(rate_limit(settings.RATE_LIMIT_DEFAULT)),
):
    product = await service.create_product(
        name=body.name,
        description=body.description,
        price=body.price,
        image_front=body.image_front,
        image_back=body.image_back,
        condition=body.condition,
        created_by_user_id=user_id,
    )
    return {"success": True, "data": product}


@router.post(
    "/{product_id:int}/auctions",
    response_model=dict,
    status_code=201,
    description="Create an auction for a product. Images must match product or are copied. P.IVA: optional video_url, buy_now.",
)
async def create_auction_for_product(
    product_id: int,
    body: AuctionCreate,
    user_id_and_piva: Annotated[tuple[UUID, bool], Depends(get_current_user_id_and_piva)],
    product_svc: ProductService = Depends(get_product_service),
    auction_svc: AuctionService = Depends(get_auction_service),
    _rate_limit: None = Depends(rate_limit(settings.RATE_LIMIT_DEFAULT)),
):
    user_id, has_piva = user_id_and_piva
    product = await product_svc.get_product_by_id(product_id)
    if not product:
        raise ProductNotFoundError()
    data = body.model_dump(exclude_none=False)
    data["product_id"] = product_id
    data["product"] = None  # use existing product, do not create inline
    data["title"] = data.get("title") or product.get("name", "")
    data["description"] = data.get("description") or product.get("description", "")
    data["created_by_user_id"] = user_id
    data["has_piva"] = has_piva
    auction = await auction_svc.create_auction(data)
    return {"success": True, "data": auction}
