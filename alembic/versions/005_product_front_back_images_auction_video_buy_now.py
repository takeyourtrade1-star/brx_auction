"""Product: image_front, image_back. Auction: image_front, image_back, video_url, buy_now.

Revision ID: 005
Revises: 004
Create Date: 2025-03-13 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Products: replace images (ARRAY) with image_front, image_back
    op.add_column(
        "products",
        sa.Column("image_front", sa.Text(), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("image_back", sa.Text(), nullable=True),
    )
    # Migrate existing images: first -> front, second -> back (if any)
    op.execute(
        sa.text("""
            UPDATE products p
            SET image_front = p.images[1],
                image_back  = CASE WHEN array_length(p.images, 1) >= 2 THEN p.images[2] ELSE NULL END
            WHERE p.images IS NOT NULL AND array_length(p.images, 1) >= 1
        """)
    )
    op.drop_column("products", "images")

    # Auctions: add image_front, image_back (required at app level; nullable in DB for backfill)
    op.add_column(
        "auctions",
        sa.Column("image_front", sa.Text(), nullable=True),
    )
    op.add_column(
        "auctions",
        sa.Column("image_back", sa.Text(), nullable=True),
    )
    # P.IVA sellers: video and buy-it-now
    op.add_column(
        "auctions",
        sa.Column("video_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "auctions",
        sa.Column("buy_now_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "auctions",
        sa.Column("buy_now_price", sa.Float(), nullable=True),
    )
    op.add_column(
        "auctions",
        sa.Column("buy_now_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("auctions", "buy_now_url")
    op.drop_column("auctions", "buy_now_price")
    op.drop_column("auctions", "buy_now_enabled")
    op.drop_column("auctions", "video_url")
    op.drop_column("auctions", "image_back")
    op.drop_column("auctions", "image_front")

    op.add_column(
        "products",
        sa.Column("images", postgresql.ARRAY(sa.Text()), nullable=True),
    )
    op.execute(
        sa.text("""
            UPDATE products
            SET images = array_remove(ARRAY[image_front, image_back], NULL)
            WHERE image_front IS NOT NULL OR image_back IS NOT NULL
        """)
    )
    op.drop_column("products", "image_back")
    op.drop_column("products", "image_front")
