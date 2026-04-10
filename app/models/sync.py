"""
SQLAlchemy models for sync schema: user_sync_settings, user_inventory_items, sync_operations.
Maps to PostgreSQL schema from schema.sql (BRX Sync).
"""
import enum
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base


class SyncStatusEnum(str, enum.Enum):
    idle = "idle"
    initial_sync = "initial_sync"
    active = "active"
    error = "error"


class UserSyncSettings(Base):
    __tablename__ = "user_sync_settings"

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    cardtrader_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sync_status: Mapped[SyncStatusEnum] = mapped_column(
        Enum(SyncStatusEnum), nullable=False, default=SyncStatusEnum.idle
    )
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("idx_sync_settings_status", "sync_status"),)


class UserInventoryItem(Base):
    __tablename__ = "user_inventory_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    blueprint_id: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    properties: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    external_stock_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_data_field: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    graded: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "blueprint_id", "external_stock_id", name="uq_inventory_user_blueprint_stock"),
        Index("idx_inventory_user_id", "user_id"),
        Index("idx_inventory_blueprint_id", "blueprint_id"),
        Index("idx_inventory_external_stock_id", "external_stock_id"),
        Index("idx_inventory_updated_at", "updated_at"),
    )


class SyncOperation(Base):
    __tablename__ = "sync_operations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    operation_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    operation_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_sync_ops_user_id", "user_id"),
        Index("idx_sync_ops_operation_id", "operation_id"),
        Index("idx_sync_ops_status", "status"),
    )
