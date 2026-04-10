"""
Pydantic schemas for bids. Monetary fields use Decimal to avoid float rounding issues.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class BidCreate(BaseModel):
    """
    Body for placing a bid. User is identified by JWT (Bearer) only; do not add userId
    to the body (extra='forbid' rejects it). This avoids invalid UUID strings causing
    uncaught exceptions or unclear errors; use Depends(get_current_user_id) in the API.
    """
    amount: Decimal = Field(..., ge=0)
    maxAmount: Optional[Decimal] = Field(None, ge=0)

    model_config = ConfigDict(extra="forbid")


class BidResponse(BaseModel):
    id: int
    auction_id: int
    user_id: UUID
    amount: Decimal
    max_amount: Optional[Decimal] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PlaceBidResult(BaseModel):
    auction: dict
    bids: list[BidResponse]
