"""
Pydantic schemas for auctions (request/response). Pagination for list.
Monetary fields use Decimal to avoid float rounding issues.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, model_validator

from app.schemas.product import ProductCreateForAuction


class AuctionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="", max_length=10_000)
    starting_price: Decimal = Field(..., ge=0)
    reserve_price: Optional[Decimal] = Field(None, ge=0)
    start_time: datetime
    end_time: datetime
    product_id: Optional[int] = Field(None, gt=0, description="Existing product id; use this OR product, not both.")
    product: Optional[ProductCreateForAuction] = Field(None, description="Inline product when creating new; use this OR product_id.")
    # Front/back images: required. When product_id set, must match the product's images; when product inline, come from product.
    image_front: str = Field(..., max_length=2048, description="URL or path of front image")
    image_back: str = Field(..., max_length=2048, description="URL or path of back image")
    # P.IVA only: video and buy-it-now
    video_url: Optional[str] = Field(None, max_length=2048, description="Product video URL (venditori con P.IVA only)")
    buy_now_enabled: Optional[bool] = Field(False, description="Enable buy-it-now linking to platform sale page (P.IVA only)")
    buy_now_url: Optional[str] = Field(
        None, max_length=2048,
        description="URL to product sale page on platform (required if buy_now_enabled). User is redirected here to buy without bidding.",
    )
    buy_now_price: Optional[Decimal] = Field(
        None, ge=0,
        description="Price shown for buy-it-now option. If not set and buy_now_enabled, defaults to product price. P.IVA only.",
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def product_or_product_id(self):
        if self.product_id is not None and self.product is not None:
            raise ValueError("Provide either product_id (existing product) or product (inline), not both.")
        if self.product_id is None and self.product is None:
            raise ValueError("Provide either product_id (existing product) or product (inline product data).")
        return self


class AuctionUpdate(BaseModel):
    """Partial update for auction (e.g. enable buy-it-now during ACTIVE auction). P.IVA only for video/buy_now."""
    video_url: Optional[str] = Field(None, max_length=2048)
    buy_now_enabled: Optional[bool] = None
    buy_now_url: Optional[str] = Field(None, max_length=2048, description="URL to product sale page (required if buy_now_enabled)")
    buy_now_price: Optional[Decimal] = Field(None, ge=0, description="Price shown for buy-it-now (optional; defaults to product price)")

    model_config = ConfigDict(extra="forbid")


class AuctionResponse(BaseModel):
    id: int
    title: str
    description: str
    starting_price: Decimal
    current_price: Decimal
    reserve_price: Optional[Decimal] = None
    start_time: datetime
    end_time: datetime
    status: str
    highest_bidder_id: Optional[UUID] = None
    product_id: Optional[str] = None
    image_front: str = ""
    image_back: str = ""
    video_url: Optional[str] = None
    buy_now_enabled: bool = False
    buy_now_price: Optional[Decimal] = None
    buy_now_url: Optional[str] = None
    winner_id: Optional[UUID] = None
    reserve_not_reached_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AuctionListResponse(BaseModel):
    items: list[AuctionResponse]
    total: Optional[int] = None
    limit: int
    offset: int
