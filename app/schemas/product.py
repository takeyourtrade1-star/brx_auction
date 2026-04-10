"""
Pydantic schemas for products. Monetary fields use Decimal to avoid float rounding issues.
"""
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict

MAX_IMAGE_URL_LENGTH = 2048


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="", max_length=10_000)
    price: Decimal = Field(default=Decimal("0"), ge=0)
    image_front: str = Field(..., max_length=MAX_IMAGE_URL_LENGTH, description="URL or path of front image")
    image_back: str = Field(..., max_length=MAX_IMAGE_URL_LENGTH, description="URL or path of back image")
    condition: str = Field(..., max_length=100, description="Product condition (e.g. NM, EX, LP)")

    model_config = ConfigDict(extra="forbid")


class ProductCreateForAuction(BaseModel):
    """Product data when creating a product inline during auction creation (no price; price comes from auction)."""
    name: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="", max_length=10_000)
    image_front: str = Field(..., max_length=MAX_IMAGE_URL_LENGTH, description="Front image (required for new product)")
    image_back: str = Field(..., max_length=MAX_IMAGE_URL_LENGTH, description="Back image (required for new product)")
    condition: str = Field(..., max_length=100, description="Product condition (e.g. NM, EX, LP)")

    model_config = ConfigDict(extra="forbid")


class ProductResponse(BaseModel):
    id: int
    name: str
    description: str
    price: Decimal
    image_front: str
    image_back: str
    condition: str

    model_config = ConfigDict(from_attributes=True)


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: Optional[int] = None
    limit: int
    offset: int
