"""Product: add images and condition. Auction: drop seller_username and array fields.

Revision ID: 004
Revises: 003
Create Date: 2025-01-04 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("images", postgresql.ARRAY(sa.Text()), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("condition", sa.String(100), nullable=True),
    )
    op.drop_column("auctions", "seller_username")
    op.drop_column("auctions", "game")
    op.drop_column("auctions", "card_name")
    op.drop_column("auctions", "condition")
    op.drop_column("auctions", "images")


def downgrade() -> None:
    op.add_column(
        "auctions",
        sa.Column("images", postgresql.ARRAY(sa.Text()), nullable=True),
    )
    op.add_column(
        "auctions",
        sa.Column("condition", postgresql.ARRAY(sa.Text()), nullable=True),
    )
    op.add_column(
        "auctions",
        sa.Column("card_name", postgresql.ARRAY(sa.Text()), nullable=True),
    )
    op.add_column(
        "auctions",
        sa.Column("game", postgresql.ARRAY(sa.Text()), nullable=True),
    )
    op.add_column(
        "auctions",
        sa.Column("seller_username", sa.String(255), nullable=True),
    )
    op.drop_column("products", "condition")
    op.drop_column("products", "images")
