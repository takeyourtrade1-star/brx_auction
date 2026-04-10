"""Initial schema: sync tables, auctions, bids, products.

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sync enum and tables (from schema.sql)
    sync_status = postgresql.ENUM("idle", "initial_sync", "active", "error", name="sync_status_enum", create_type=True)
    sync_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "user_sync_settings",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cardtrader_token_encrypted", sa.Text(), nullable=False),
        sa.Column("webhook_secret", sa.String(255), nullable=True),
        sa.Column("sync_status", sync_status, nullable=False, server_default="idle"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("idx_sync_settings_status", "user_sync_settings", ["sync_status"], unique=False)

    op.create_table(
        "user_inventory_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("blueprint_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("properties", postgresql.JSONB(), nullable=True),
        sa.Column("external_stock_id", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("user_data_field", sa.Text(), nullable=True),
        sa.Column("graded", sa.Boolean(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "blueprint_id", "external_stock_id", name="uq_inventory_user_blueprint_stock"),
    )
    op.create_index("idx_inventory_user_id", "user_inventory_items", ["user_id"], unique=False)
    op.create_index("idx_inventory_blueprint_id", "user_inventory_items", ["blueprint_id"], unique=False)
    op.create_index("idx_inventory_external_stock_id", "user_inventory_items", ["external_stock_id"], unique=False)
    op.create_index("idx_inventory_updated_at", "user_inventory_items", ["updated_at"], unique=False)

    op.create_table(
        "sync_operations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_id", sa.String(255), nullable=False),
        sa.Column("operation_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("operation_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_id", name="sync_operations_operation_id_key"),
    )
    op.create_index("idx_sync_ops_user_id", "sync_operations", ["user_id"], unique=False)
    op.create_index("idx_sync_ops_operation_id", "sync_operations", ["operation_id"], unique=False)
    op.create_index("idx_sync_ops_status", "sync_operations", ["status"], unique=False)

    # Marketplace: auctions, bids, products
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "auctions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("seller_username", sa.String(255), nullable=True),
        sa.Column("starting_price", sa.Float(), nullable=False),
        sa.Column("current_price", sa.Float(), nullable=False),
        sa.Column("reserve_price", sa.Float(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("highest_bidder_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_id", sa.String(100), nullable=True),
        sa.Column("game", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("card_name", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("condition", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("images", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "bids",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("auction_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("max_amount", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["auction_id"], ["auctions.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("bids")
    op.drop_table("auctions")
    op.drop_table("products")
    op.drop_index("idx_sync_ops_status", "sync_operations")
    op.drop_index("idx_sync_ops_operation_id", "sync_operations")
    op.drop_index("idx_sync_ops_user_id", "sync_operations")
    op.drop_table("sync_operations")
    op.drop_index("idx_inventory_updated_at", "user_inventory_items")
    op.drop_index("idx_inventory_external_stock_id", "user_inventory_items")
    op.drop_index("idx_inventory_blueprint_id", "user_inventory_items")
    op.drop_index("idx_inventory_user_id", "user_inventory_items")
    op.drop_table("user_inventory_items")
    op.drop_index("idx_sync_settings_status", "user_sync_settings")
    op.drop_table("user_sync_settings")
    postgresql.ENUM(name="sync_status_enum").drop(op.get_bind(), checkfirst=True)
