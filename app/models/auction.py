"""
SQLAlchemy model for auctions (marketplace). Status: DRAFT | ACTIVE | CLOSED.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class Auction(Base):
    __tablename__ = "auctions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    starting_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[float] = mapped_column(Float, nullable=False)
    reserve_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")  # DRAFT | ACTIVE | CLOSED
    highest_bidder_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_by_user_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    product_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    image_front: Mapped[str] = mapped_column(Text, nullable=False)
    image_back: Mapped[str] = mapped_column(Text, nullable=False)
    video_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # P.IVA only
    buy_now_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # P.IVA only
    # buy_now_price: price shown for "buy it now" (optional; defaults to product price when buy_now_enabled)
    buy_now_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # buy_now_url: link to product sale page; user is redirected here to buy without bidding (required if buy_now_enabled)
    buy_now_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # relationship to bids (optional, for ORM loading)
    # bids: Mapped[list["Bid"]] = relationship("Bid", back_populates="auction", lazy="selectin")
